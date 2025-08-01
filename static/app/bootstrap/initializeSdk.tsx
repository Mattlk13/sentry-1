// eslint-disable-next-line simple-import-sort/imports
import * as Sentry from '@sentry/react';
import type {Event} from '@sentry/core';

import {SENTRY_RELEASE_VERSION, SPA_DSN} from 'sentry/constants';
import type {Config} from 'sentry/types/system';
import {addExtraMeasurements, addUIElementTag} from 'sentry/utils/performanceForSentry';
import normalizeUrl from 'sentry/utils/url/normalizeUrl';
import {
  createRoutesFromChildren,
  matchRoutes,
  useLocation,
  useNavigationType,
} from 'react-router-dom';
import {useEffect} from 'react';

const SPA_MODE_ALLOW_URLS = [
  'localhost',
  'dev.getsentry.net',
  'sentry.dev',
  'webpack-internal://',
];

const SPA_MODE_TRACE_PROPAGATION_TARGETS = [
  'localhost',
  'dev.getsentry.net',
  'sentry.dev',
];

let lastEventId: string | undefined;

export function getLastEventId(): string | undefined {
  return lastEventId;
}

// We don't care about recording breadcrumbs for these hosts. These typically
// pollute our breadcrumbs since they may occur a LOT.
//
// XXX(epurkhiser): Note some of these hosts may only apply to sentry.io.
const IGNORED_BREADCRUMB_FETCH_HOSTS = ['amplitude.com', 'reload.getsentry.net'];

// Ignore analytics in spans as well
const IGNORED_SPANS_BY_DESCRIPTION = ['amplitude.com', 'reload.getsentry.net'];

// We check for `window.__initialData.user` property and only enable profiling
// for Sentry employees. This is to prevent a Violation error being visible in
// the browser console for our users.
const shouldOverrideBrowserProfiling = window?.__initialData?.user?.isSuperuser;
/**
 * We accept a routes argument here because importing `static/routes`
 * is expensive in regards to bundle size. Some entrypoints may opt to forgo
 * having routing instrumentation in order to have a smaller bundle size.
 * (e.g.  `static/views/integrationPipeline`)
 */
function getSentryIntegrations() {
  const integrations = [
    Sentry.extraErrorDataIntegration({
      // 6 is arbitrary, seems like a nice number
      depth: 6,
    }),
    Sentry.reactRouterV6BrowserTracingIntegration({
      useEffect,
      useLocation,
      useNavigationType,
      createRoutesFromChildren,
      matchRoutes,
      _experiments: {
        enableStandaloneClsSpans: true,
        enableStandaloneLcpSpans: true,
      },
      linkPreviousTrace: 'session-storage',
    }),
    Sentry.browserProfilingIntegration(),
    Sentry.thirdPartyErrorFilterIntegration({
      filterKeys: ['sentry-spa'],
      behaviour: 'apply-tag-if-contains-third-party-frames',
    }),
    Sentry.featureFlagsIntegration(),
  ];

  return integrations;
}

/**
 * Initialize the Sentry SDK
 *
 * If `routes` is passed, we will instrument react-router. Not all
 * entrypoints require this.
 */
export function initializeSdk(config: Config) {
  // NOTE: This config is mutated by `commonInitialization`
  const {apmSampling, sentryConfig, userIdentity} = config;
  const tracesSampleRate = apmSampling ?? 0;
  const extraTracePropagationTargets = SPA_DSN
    ? SPA_MODE_TRACE_PROPAGATION_TARGETS
    : [...sentryConfig.tracePropagationTargets];

  Sentry.init({
    ...sentryConfig,
    /**
     * For SPA mode, we need a way to overwrite the default DSN from backend
     * as well as `allowUrls`
     */
    dsn: SPA_DSN || sentryConfig?.dsn,
    /**
     * Frontend can be built with a `SENTRY_RELEASE_VERSION` environment
     * variable for release string, useful if frontend is deployed separately
     * from backend.
     */
    release: SENTRY_RELEASE_VERSION ?? sentryConfig?.release,
    allowUrls: SPA_DSN ? SPA_MODE_ALLOW_URLS : sentryConfig?.allowUrls,
    integrations: getSentryIntegrations(),
    tracesSampleRate,
    profilesSampleRate: shouldOverrideBrowserProfiling ? 1 : 0.1,
    tracePropagationTargets: ['localhost', /^\//, ...extraTracePropagationTargets],
    tracesSampler: context => {
      const op = context.attributes?.[Sentry.SEMANTIC_ATTRIBUTE_SENTRY_OP] || '';
      if (op.startsWith('ui.action')) {
        return tracesSampleRate / 100;
      }
      return tracesSampleRate;
    },
    beforeSendTransaction(event) {
      addExtraMeasurements(event);
      addUIElementTag(event);

      const filteredSpans = event.spans?.filter(span => {
        return IGNORED_SPANS_BY_DESCRIPTION.every(
          partialDesc => !span.description?.includes(partialDesc)
        );
      });

      // If we removed any spans at the end above, the end timestamp needs to be adjusted again.
      if (filteredSpans && filteredSpans?.length !== event.spans?.length) {
        event.spans = filteredSpans;
        const newEndTimestamp = Math.max(...event.spans.map(span => span.timestamp ?? 0));
        event.timestamp = newEndTimestamp;
      }

      if (event.transaction) {
        event.transaction = normalizeUrl(event.transaction, {forceCustomerDomain: true});
      }
      return event;
    },

    ignoreErrors: [
      /**
       * There is a bug in Safari, that causes `AbortError` when fetch is
       * aborted, and you are in the middle of reading the response. In Chrome
       * and other browsers, it is handled gracefully, where in Safari, it
       * produces additional error, that is jumping outside of the original
       * Promise chain and bubbles up to the `unhandledRejection` handler, that
       * we then captures as error.
       *
       * Ref: https://bugs.webkit.org/show_bug.cgi?id=215771
       */
      /AbortError: Fetch is aborted/i,
      /AbortError: The operation was aborted/i,
      /AbortError: signal is aborted without reason/i,
      /AbortError: The user aborted a request/i,
      /**
       * React internal error thrown when something outside react modifies the DOM
       * This is usually because of a browser extension or chrome translate page
       */
      "NotFoundError: Failed to execute 'removeChild' on 'Node': The node to be removed is not a child of this node.",
      "NotFoundError: Failed to execute 'insertBefore' on 'Node': The node before which the new node is to be inserted is not a child of this node.",
    ],

    beforeBreadcrumb(crumb) {
      const isFetch = crumb.category === 'fetch' || crumb.category === 'xhr';

      // Ignore
      if (
        isFetch &&
        IGNORED_BREADCRUMB_FETCH_HOSTS.some(host => crumb.data?.url?.includes(host))
      ) {
        return null;
      }

      return crumb;
    },

    beforeSend(event, hint) {
      if (isFilteredRequestErrorEvent(event) || isEventWithFileUrl(event)) {
        return null;
      }

      handlePossibleUndefinedResponseBodyErrors(event);
      addEndpointTagToRequestError(event);
      lastEventId = event.event_id || hint.event_id;

      return event;
    },
    enableLogs: true,
  });

  // Track timeOrigin Selection by the SDK to see if it improves transaction durations
  Sentry.addEventProcessor((event: Sentry.Event, _hint?: Sentry.EventHint) => {
    event.tags = event.tags || {};
    return event;
  });

  if (userIdentity) {
    Sentry.setUser(userIdentity);
  }
  if (window.__SENTRY__VERSION) {
    Sentry.setTag('sentry_version', window.__SENTRY__VERSION);
  }

  const {customerDomain} = window.__initialData;

  if (customerDomain) {
    Sentry.setTag('isCustomerDomain', 'yes');
    Sentry.setTag('customerDomain.organizationUrl', customerDomain.organizationUrl);
    Sentry.setTag('customerDomain.sentryUrl', customerDomain.sentryUrl);
    Sentry.setTag('customerDomain.subdomain', customerDomain.subdomain);
  }
}

export function isFilteredRequestErrorEvent(event: Event): boolean {
  const exceptionValues = event.exception?.values;

  if (!exceptionValues) {
    return false;
  }

  // In case there's a chain, we take the last entry, because that's the one
  // passed to `captureException`, and the one right before that, since
  // `RequestError`s are used as the main error's `cause` value in
  // `handleXhrErrorResponse`
  const mainAndMaybeCauseErrors = exceptionValues.slice(-2);

  for (const error of mainAndMaybeCauseErrors) {
    const {type = '', value = ''} = error;

    const is200 =
      ['RequestError'].includes(type) && !!value.match('(GET|POST|PUT|DELETE) .* 200');
    const is400 =
      ['BadRequestError', 'RequestError'].includes(type) &&
      !!value.match('(GET|POST|PUT|DELETE) .* 400');
    const is401 =
      ['UnauthorizedError', 'RequestError'].includes(type) &&
      !!value.match('(GET|POST|PUT|DELETE) .* 401');
    const is403 =
      ['ForbiddenError', 'RequestError'].includes(type) &&
      !!value.match('(GET|POST|PUT|DELETE) .* 403');
    const is404 =
      ['NotFoundError', 'RequestError'].includes(type) &&
      !!value.match('(GET|POST|PUT|DELETE) .* 404');
    const is429 =
      ['TooManyRequestsError', 'RequestError'].includes(type) &&
      !!value.match('(GET|POST|PUT|DELETE) .* 429');

    if (is200 || is400 || is401 || is403 || is404 || is429) {
      return true;
    }
  }

  return false;
}

export function isEventWithFileUrl(event: Event): boolean {
  return !!event.request?.url?.startsWith('file://');
}

/** Tag and set fingerprint for UndefinedResponseBodyError events */
function handlePossibleUndefinedResponseBodyErrors(event: Event): void {
  // One or both of these may be undefined, depending on the type of event
  const [mainError, causeError] = event.exception?.values?.slice(-2).reverse() || [];

  const mainErrorIsURBE = mainError?.type === 'UndefinedResponseBodyError';
  const causeErrorIsURBE = causeError?.type === 'UndefinedResponseBodyError';

  if (mainErrorIsURBE || causeErrorIsURBE) {
    mainError!.type = 'UndefinedResponseBodyError';
    event.tags = {...event.tags, undefinedResponseBody: true};
    event.fingerprint = mainErrorIsURBE
      ? ['UndefinedResponseBodyError as main error']
      : ['UndefinedResponseBodyError as cause error'];
  }
}

export function addEndpointTagToRequestError(event: Event): void {
  const errorMessage = event.exception?.values?.[0]!.value || '';

  // The capturing group here turns `GET /dogs/are/great 500` into just `GET /dogs/are/great`
  const requestErrorRegex = new RegExp('^([A-Za-z]+ (/[^/]+)+/) \\d+$');
  const messageMatch = requestErrorRegex.exec(errorMessage);

  if (messageMatch) {
    event.tags = {...event.tags, endpoint: messageMatch[1]};
  }
}
