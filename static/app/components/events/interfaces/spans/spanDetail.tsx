import {Fragment, useEffect, useState} from 'react';
import {useTheme} from '@emotion/react';
import styled from '@emotion/styled';
import omit from 'lodash/omit';

import {CopyToClipboardButton} from 'sentry/components/copyToClipboardButton';
import {Alert} from 'sentry/components/core/alert';
import {Button} from 'sentry/components/core/button';
import {LinkButton} from 'sentry/components/core/button/linkButton';
import {ExternalLink, Link} from 'sentry/components/core/link';
import {DateTime} from 'sentry/components/dateTime';
import DiscoverButton from 'sentry/components/discoverButton';
import SpanSummaryButton from 'sentry/components/events/interfaces/spans/spanSummaryButton';
import {OpsDot} from 'sentry/components/events/opsBreakdown';
import FileSize from 'sentry/components/fileSize';
import LoadingIndicator from 'sentry/components/loadingIndicator';
import {
  ErrorDot,
  ErrorLevel,
  ErrorMessageContent,
  ErrorMessageTitle,
  ErrorTitle,
} from 'sentry/components/performance/waterfall/rowDetails';
import Pill from 'sentry/components/pill';
import Pills from 'sentry/components/pills';
import {TransactionToProfileButton} from 'sentry/components/profiling/transactionToProfileButton';
import {
  generateIssueEventTarget,
  generateTraceTarget,
} from 'sentry/components/quickTrace/utils';
import {ALL_ACCESS_PROJECTS, PAGE_URL_PARAM} from 'sentry/constants/pageFilters';
import {t, tn} from 'sentry/locale';
import {space} from 'sentry/styles/space';
import type {EventTransaction} from 'sentry/types/event';
import type {Organization} from 'sentry/types/organization';
import {assert} from 'sentry/types/utils';
import {defined} from 'sentry/utils';
import {trackAnalytics} from 'sentry/utils/analytics';
import EventView from 'sentry/utils/discover/eventView';
import {SavedQueryDatasets} from 'sentry/utils/discover/types';
import {generateEventSlug} from 'sentry/utils/discover/urls';
import getDynamicText from 'sentry/utils/getDynamicText';
import type {
  QuickTraceEvent,
  TraceErrorOrIssue,
} from 'sentry/utils/performance/quickTrace/types';
import {useLocation} from 'sentry/utils/useLocation';
import useProjects from 'sentry/utils/useProjects';
import {hasDatasetSelector} from 'sentry/views/dashboards/utils';
import {spanDetailsRouteWithQuery} from 'sentry/views/performance/transactionSummary/transactionSpans/spanDetails/utils';
import {transactionSummaryRouteWithQuery} from 'sentry/views/performance/transactionSummary/utils';
import {getPerformanceDuration} from 'sentry/views/performance/utils/getPerformanceDuration';

import {SpanEntryContext} from './context';
import {GapSpanDetails} from './gapSpanDetails';
import InlineDocs from './inlineDocs';
import {SpanProfileDetails} from './spanProfileDetails';
import type {ParsedTraceType, ProcessedSpanType, RawSpanType} from './types';
import {rawSpanKeys} from './types';
import type {SubTimingInfo} from './utils';
import {
  getCumulativeAlertLevelFromErrors,
  getFormattedTimeRangeWithLeadingAndTrailingZero,
  getSpanSubTimings,
  getTraceDateTimeRange,
  isErrorPerformanceError,
  isGapSpan,
  isHiddenDataKey,
  isOrphanSpan,
  scrollToSpan,
} from './utils';

const DEFAULT_ERRORS_VISIBLE = 5;

const SIZE_DATA_KEYS = [
  'Encoded Body Size',
  'Decoded Body Size',
  'Transfer Size',
  'http.request_content_length',
  'http.response_content_length',
  'http.decoded_response_content_length',
  'http.response_transfer_size',
];

type TransactionResult = {
  id: string;
  'project.name': string;
  'trace.span': string;
  transaction: string;
};

type Props = {
  childTransactions: QuickTraceEvent[] | null;
  event: Readonly<EventTransaction>;
  isRoot: boolean;
  organization: Organization;
  relatedErrors: TraceErrorOrIssue[] | null;
  resetCellMeasureCache: () => void;
  scrollToHash: (hash: string) => void;
  span: ProcessedSpanType;
  trace: Readonly<ParsedTraceType>;
};

function SpanDetail(props: Props) {
  const theme = useTheme();
  const [errorsOpened, setErrorsOpened] = useState(false);
  const location = useLocation();
  const profileId = props.event.contexts.profile?.profile_id;
  const {projects} = useProjects();
  const project = projects.find(p => p.id === props.event.projectID);

  useEffect(() => {
    // Run on mount.

    const {span, organization, event} = props;
    if (!('op' in span)) {
      return;
    }

    trackAnalytics('performance_views.event_details.open_span_details', {
      organization,
      operation: span.op ?? 'undefined',
      origin: span.origin ?? 'undefined',
      project_platform: event.platform ?? 'undefined',
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function renderTraversalButton(): React.ReactNode {
    if (!props.childTransactions) {
      // TODO: Amend size to use theme when we eventually refactor LoadingIndicator
      // 12px is consistent with theme.iconSizes['xs'] but theme returns a string.
      return (
        <StyledDiscoverButton href="#" size="xs" disabled>
          <StyledLoadingIndicator size={16} />
        </StyledDiscoverButton>
      );
    }

    if (props.childTransactions.length <= 0) {
      return null;
    }

    const {span, trace, event, organization} = props;

    assert(!isGapSpan(span));

    if (props.childTransactions.length === 1) {
      // Note: This is rendered by renderSpanChild() as a dedicated row
      return null;
    }

    const {start, end} = getTraceDateTimeRange({
      start: trace.traceStartTimestamp,
      end: trace.traceEndTimestamp,
    });

    const childrenEventView = EventView.fromSavedQuery({
      id: undefined,
      name: `Children from Span ID ${span.span_id}`,
      fields: [
        'transaction',
        'project',
        'trace.span',
        'transaction.duration',
        'timestamp',
      ],
      orderby: '-timestamp',
      query: `event.type:transaction trace:${span.trace_id} trace.parent_span:${span.span_id}`,
      projects: organization.features.includes('global-views')
        ? [ALL_ACCESS_PROJECTS]
        : [Number(event.projectID)],
      version: 2,
      start,
      end,
    });

    return (
      <StyledDiscoverButton
        data-test-id="view-child-transactions"
        size="xs"
        to={childrenEventView.getResultsViewUrlTarget(
          organization,
          false,
          hasDatasetSelector(organization) ? SavedQueryDatasets.TRANSACTIONS : undefined
        )}
      >
        {t('View Children')}
      </StyledDiscoverButton>
    );
  }

  function renderSpanChild(): React.ReactNode {
    const {childTransactions, organization} = props;

    if (!childTransactions || childTransactions.length !== 1) {
      return null;
    }

    const childTransaction = childTransactions[0]!;

    const transactionResult: TransactionResult = {
      'project.name': childTransaction.project_slug,
      transaction: childTransaction.transaction,
      'trace.span': childTransaction.span_id,
      id: childTransaction.event_id,
    };

    const eventSlug = generateSlug(transactionResult);

    const viewChildButton = (
      <SpanEntryContext.Consumer>
        {({getViewChildTransactionTarget}) => {
          const to = getViewChildTransactionTarget({
            ...transactionResult,
            eventSlug,
          });

          if (!to) {
            return null;
          }

          const target = transactionSummaryRouteWithQuery({
            organization,
            transaction: transactionResult.transaction,
            query: omit(location.query, Object.values(PAGE_URL_PARAM)),
            projectID: String(childTransaction.project_id),
          });

          return (
            <ButtonGroup>
              <LinkButton data-test-id="view-child-transaction" size="xs" to={to}>
                {t('View Transaction')}
              </LinkButton>
              <LinkButton size="xs" to={target}>
                {t('View Summary')}
              </LinkButton>
            </ButtonGroup>
          );
        }}
      </SpanEntryContext.Consumer>
    );

    return (
      <Row title="Child Transaction" extra={viewChildButton}>
        {`${transactionResult.transaction} (${transactionResult['project.name']})`}
      </Row>
    );
  }

  function renderTraceButton() {
    const {span, organization, event} = props;

    if (isGapSpan(span)) {
      return null;
    }

    return (
      <LinkButton size="xs" to={generateTraceTarget(event, organization, location)}>
        {t('View Trace')}
      </LinkButton>
    );
  }

  function renderSpanDetailActions() {
    const {span, organization, event} = props;

    if (isGapSpan(span) || !span.op || !span.hash) {
      return null;
    }

    const transactionName = event.title;

    return (
      <ButtonGroup>
        <SpanSummaryButton event={event} organization={organization} span={span} />
        <LinkButton
          size="xs"
          to={spanDetailsRouteWithQuery({
            organization,
            transaction: transactionName,
            query: location.query,
            spanSlug: {op: span.op, group: span.hash},
            projectID: event.projectID,
          })}
        >
          {t('View Similar Spans')}
        </LinkButton>
      </ButtonGroup>
    );
  }

  function renderOrphanSpanMessage() {
    const {span} = props;

    if (!isOrphanSpan(span)) {
      return null;
    }

    return (
      <Alert.Container>
        <Alert type="info" system>
          {t(
            'This is a span that has no parent span within this transaction. It has been attached to the transaction root span by default.'
          )}
        </Alert>
      </Alert.Container>
    );
  }

  function toggleErrors() {
    setErrorsOpened(prevErrorsOpened => !prevErrorsOpened);
  }

  function renderSpanErrorMessage() {
    const {span, organization, relatedErrors} = props;

    if (!relatedErrors || relatedErrors.length <= 0 || isGapSpan(span)) {
      return null;
    }

    const visibleErrors = errorsOpened
      ? relatedErrors
      : relatedErrors.slice(0, DEFAULT_ERRORS_VISIBLE);

    return (
      <Alert.Container>
        <Alert type={getCumulativeAlertLevelFromErrors(relatedErrors) ?? 'info'} system>
          <ErrorMessageTitle>
            {tn(
              '%s error event or performance issue is associated with this span.',
              '%s error events or performance issues are associated with this span.',
              relatedErrors.length
            )}
          </ErrorMessageTitle>
          <Fragment>
            {visibleErrors.map(error => (
              <ErrorMessageContent
                key={error.event_id}
                excludeLevel={isErrorPerformanceError(error)}
              >
                {isErrorPerformanceError(error) ? (
                  <ErrorDot level="error" />
                ) : (
                  <Fragment>
                    <ErrorDot level={error.level} />
                    <ErrorLevel>{error.level}</ErrorLevel>
                  </Fragment>
                )}

                <ErrorTitle>
                  <Link to={generateIssueEventTarget(error, organization)}>
                    {error.title}
                  </Link>
                </ErrorTitle>
              </ErrorMessageContent>
            ))}
          </Fragment>
          {relatedErrors.length > DEFAULT_ERRORS_VISIBLE && (
            <ErrorToggle size="xs" onClick={toggleErrors}>
              {errorsOpened ? t('Show less') : t('Show more')}
            </ErrorToggle>
          )}
        </Alert>
      </Alert.Container>
    );
  }

  function partitionSizes(data: any): {
    nonSizeKeys: Record<string, unknown>;
    sizeKeys: Record<string, number>;
  } {
    const sizeKeys = SIZE_DATA_KEYS.reduce(
      (keys, key) => {
        if (data.hasOwnProperty(key) && defined(data[key])) {
          try {
            keys[key] = parseInt(data[key], 10);
          } catch (e) {
            keys[key] = data[key];
          }
        }
        return keys;
      },
      {} as Record<string, number>
    );

    const nonSizeKeys = {...data};
    SIZE_DATA_KEYS.forEach(key => delete nonSizeKeys[key]);

    return {
      sizeKeys,
      nonSizeKeys,
    };
  }

  function renderProfileMessage() {
    const {organization, span, event} = props;

    if (!organization.features.includes('profiling') || isGapSpan(span)) {
      return null;
    }

    return (
      <SpanProfileDetails
        span={{
          span_id: span.span_id,
          start_timestamp: span.start_timestamp,
          end_timestamp: span.timestamp,
        }}
        event={event}
      />
    );
  }

  function renderSpanDetails() {
    const {span, event, organization, scrollToHash} = props;

    if (isGapSpan(span)) {
      return (
        <SpanDetails>
          {organization.features.includes('profiling') ? (
            <GapSpanDetails event={event} span={span} />
          ) : (
            <InlineDocs platform={event.sdk?.name || ''} />
          )}
        </SpanDetails>
      );
    }

    const startTimestamp: number = span.start_timestamp;
    const endTimestamp: number = span.timestamp;
    const {start: startTimeWithLeadingZero, end: endTimeWithLeadingZero} =
      getFormattedTimeRangeWithLeadingAndTrailingZero(startTimestamp, endTimestamp);

    const duration = (endTimestamp - startTimestamp) * 1000;
    const durationString = `${Number(duration.toFixed(3)).toLocaleString()}ms`;

    const unknownKeys = Object.keys(span).filter(key => {
      return !isHiddenDataKey(key) && !rawSpanKeys.has(key as any);
    });

    const {sizeKeys, nonSizeKeys} = partitionSizes(span?.data ?? {});

    const allZeroSizes = SIZE_DATA_KEYS.map(key => sizeKeys[key]).every(
      value => value === 0
    );

    const timingKeys = getSpanSubTimings(span, theme) ?? [];

    return (
      <Fragment>
        {renderOrphanSpanMessage()}
        {renderSpanErrorMessage()}
        {renderProfileMessage()}
        <SpanDetails>
          <table className="table key-value">
            <tbody>
              <Row
                title={
                  isGapSpan(span) ? (
                    <SpanIdTitle>Span ID</SpanIdTitle>
                  ) : (
                    <SpanIdTitle
                      onClick={scrollToSpan(
                        span.span_id,
                        scrollToHash,
                        location,
                        organization
                      )}
                    >
                      Span ID
                    </SpanIdTitle>
                  )
                }
                extra={renderTraversalButton()}
              >
                {span.span_id}
                <CopyToClipboardButton
                  borderless
                  size="zero"
                  iconSize="xs"
                  text={`${window.location.href.replace(window.location.hash, '')}#span-${
                    span.span_id
                  }`}
                />
              </Row>
              <Row title="Parent Span ID">{span.parent_span_id || ''}</Row>
              {renderSpanChild()}
              <Row title="Trace ID" extra={renderTraceButton()}>
                {span.trace_id}
              </Row>
              {profileId && project?.slug && (
                <Row
                  title="Profile ID"
                  extra={
                    <TransactionToProfileButton
                      event={event}
                      size="xs"
                      projectSlug={project.slug}
                      query={{
                        spanId: span.span_id,
                      }}
                    >
                      {t('View Profile')}
                    </TransactionToProfileButton>
                  }
                >
                  {profileId}
                </Row>
              )}
              <Row title="Description" extra={renderSpanDetailActions()}>
                {span?.description ?? ''}
              </Row>
              <Row title="Status">{span.status || ''}</Row>
              <Row title="Start Date">
                {getDynamicText({
                  fixed: 'Mar 16, 2020 9:10:12 AM UTC',
                  value: (
                    <Fragment>
                      <DateTime date={startTimestamp * 1000} year seconds timeZone />
                      {` (${startTimeWithLeadingZero})`}
                    </Fragment>
                  ),
                })}
              </Row>
              <Row title="End Date">
                {getDynamicText({
                  fixed: 'Mar 16, 2020 9:10:13 AM UTC',
                  value: (
                    <Fragment>
                      <DateTime date={endTimestamp * 1000} year seconds timeZone />
                      {` (${endTimeWithLeadingZero})`}
                    </Fragment>
                  ),
                })}
              </Row>
              <Row title="Duration">{durationString}</Row>
              <Row title="Operation">{span.op || ''}</Row>
              <Row title="Origin">
                {span.origin === undefined ? null : String(span.origin)}
              </Row>
              <Row title="Same Process as Parent">
                {span.same_process_as_parent === undefined
                  ? null
                  : String(span.same_process_as_parent)}
              </Row>
              <Row title="Span Group">
                {defined(span.hash) ? String(span.hash) : null}
              </Row>
              <Row title="Span Self Time">
                {defined(span.exclusive_time)
                  ? `${Number(span.exclusive_time.toFixed(3)).toLocaleString()}ms`
                  : null}
              </Row>
              {timingKeys.map(timing => (
                <Row
                  title={timing.name}
                  key={timing.name}
                  prefix={<RowTimingPrefix timing={timing} />}
                >
                  {getPerformanceDuration(Number(timing.duration) * 1000)}
                </Row>
              ))}
              <Tags span={span} />
              {allZeroSizes && (
                <TextTr>
                  The following sizes were not collected for security reasons. Check if
                  the host serves the appropriate
                  <ExternalLink href="https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Timing-Allow-Origin">
                    <span className="val-string">Timing-Allow-Origin</span>
                  </ExternalLink>
                  header. You may have to enable this collection manually.
                </TextTr>
              )}
              {Object.entries(sizeKeys).map(([key, value]) => (
                <Row title={key} key={key}>
                  <Fragment>
                    <FileSize bytes={value} />
                    {value >= 1024 && <span>{` (${maybeStringify(value)} B)`}</span>}
                  </Fragment>
                </Row>
              ))}
              {Object.entries(nonSizeKeys).map(([key, value]) =>
                isHiddenDataKey(key) ? null : (
                  <Row title={key} key={key}>
                    {maybeStringify(value)}
                  </Row>
                )
              )}
              {unknownKeys.map(key => (
                <Row title={key} key={key}>
                  {maybeStringify(span[key as never])}
                </Row>
              ))}
            </tbody>
          </table>
        </SpanDetails>
      </Fragment>
    );
  }

  return (
    <SpanDetailContainer
      data-component="span-detail"
      onClick={event => {
        // prevent toggling the span detail
        event.stopPropagation();
      }}
    >
      {renderSpanDetails()}
    </SpanDetailContainer>
  );
}

function RowTimingPrefix({timing}: {timing: SubTimingInfo}) {
  return <OpsDot style={{backgroundColor: timing.color}} />;
}

function maybeStringify(value: unknown): string {
  if (typeof value === 'string') {
    return value;
  }
  return JSON.stringify(value, null, 4);
}

const StyledDiscoverButton = styled(DiscoverButton)`
  position: absolute;
  top: ${space(0.75)};
  right: ${space(0.5)};
`;

export const SpanDetailContainer = styled('div')`
  border-bottom: 1px solid ${p => p.theme.border};
  cursor: auto;
`;

export const SpanDetails = styled('div')`
  padding: ${space(2)};

  table.table.key-value td.key {
    max-width: 280px;
  }
`;

const ValueTd = styled('td')`
  position: relative;
`;

const StyledLoadingIndicator = styled(LoadingIndicator)`
  display: flex;
  align-items: center;
  margin: 0;
`;

const StyledText = styled('p')`
  font-size: ${p => p.theme.fontSize.md};
  margin: ${space(2)} 0;
`;

function TextTr({children}: any) {
  return (
    <tr>
      <td className="key" />
      <ValueTd className="value">
        <StyledText>{children}</StyledText>
      </ValueTd>
    </tr>
  );
}

const ErrorToggle = styled(Button)`
  margin-top: ${space(0.75)};
`;

const SpanIdTitle = styled('a')`
  display: flex;
  color: ${p => p.theme.textColor};
  :hover {
    color: ${p => p.theme.textColor};
  }
`;

export function Row({
  title,
  keep,
  children,
  prefix,
  extra = null,
}: {
  children: React.ReactNode;
  title: React.JSX.Element | string | null;
  extra?: React.ReactNode;
  keep?: boolean;
  prefix?: React.JSX.Element;
}) {
  if (!keep && !children) {
    return null;
  }

  return (
    <tr>
      <td className="key">
        <Flex>
          {prefix}
          {title}
        </Flex>
      </td>
      <ValueTd className="value">
        <ValueRow>
          <StyledPre>
            <span className="val-string">{children}</span>
          </StyledPre>
          <ButtonContainer>{extra}</ButtonContainer>
        </ValueRow>
      </ValueTd>
    </tr>
  );
}

function Tags({span}: {span: RawSpanType}) {
  const tags: Record<string, string> | undefined = span?.tags;

  if (!tags) {
    return null;
  }

  const keys = Object.keys(tags);

  if (keys.length <= 0) {
    return null;
  }

  return (
    <tr>
      <td className="key">Tags</td>
      <td className="value">
        <Pills style={{padding: '8px'}}>
          {keys.map((key, index) => (
            <Pill key={index} name={key} value={String(tags[key]) || ''} />
          ))}
        </Pills>
      </td>
    </tr>
  );
}

function generateSlug(result: TransactionResult): string {
  return generateEventSlug({
    id: result.id,
    'project.name': result['project.name'],
  });
}

const Flex = styled('div')`
  display: flex;
  align-items: center;
`;
const ButtonGroup = styled('div')`
  display: flex;
  flex-direction: column;
  gap: ${space(0.5)};
`;

const ValueRow = styled('div')`
  display: grid;
  grid-template-columns: auto min-content;
  gap: ${space(1)};

  border-radius: 4px;
  background-color: ${p => p.theme.surface200};
  margin: 2px;
`;

const StyledPre = styled('pre')`
  margin: 0 !important;
  background-color: transparent !important;
`;

const ButtonContainer = styled('div')`
  padding: 8px 10px;
`;

export default SpanDetail;
