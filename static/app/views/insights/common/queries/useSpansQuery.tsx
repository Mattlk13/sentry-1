import moment from 'moment-timezone';

import {defined} from 'sentry/utils';
import type {TableData} from 'sentry/utils/discover/discoverQuery';
import {useDiscoverQuery} from 'sentry/utils/discover/discoverQuery';
import type {EventsMetaType, MetaType} from 'sentry/utils/discover/eventView';
import type EventView from 'sentry/utils/discover/eventView';
import {encodeSort} from 'sentry/utils/discover/eventView';
import type {DiscoverQueryProps} from 'sentry/utils/discover/genericDiscoverQuery';
import {useGenericDiscoverQuery} from 'sentry/utils/discover/genericDiscoverQuery';
import {DiscoverDatasets} from 'sentry/utils/discover/types';
import {intervalToMilliseconds} from 'sentry/utils/duration/intervalToMilliseconds';
import {useLocation} from 'sentry/utils/useLocation';
import useOrganization from 'sentry/utils/useOrganization';
import usePageFilters from 'sentry/utils/usePageFilters';
import type {
  SamplingMode,
  SpansRPCQueryExtras,
} from 'sentry/views/explore/hooks/useProgressiveQuery';
import {
  getRetryDelay,
  shouldRetryHandler,
} from 'sentry/views/insights/common/utils/retryHandlers';
import {TrackResponse} from 'sentry/views/insights/common/utils/trackResponse';

export const DATE_FORMAT = 'YYYY-MM-DDTHH:mm:ssZ';

const SEVEN_DAYS = 7 * 24 * 60 * 60 * 1000;
const FOURTEEN_DAYS = 14 * 24 * 60 * 60 * 1000;
const THIRTY_DAYS = 30 * 24 * 60 * 60 * 1000;
const SIXTY_DAYS = 60 * 24 * 60 * 60 * 1000;

export function useSpansQuery<T = any[]>({
  eventView,
  initialData,
  limit,
  enabled,
  referrer = 'use-spans-query',
  allowAggregateConditions,
  cursor,
  trackResponseAnalytics = true,
  queryExtras,
}: {
  allowAggregateConditions?: boolean;
  cursor?: string;
  enabled?: boolean;
  eventView?: EventView;
  initialData?: T;
  limit?: number;
  queryExtras?: SpansRPCQueryExtras;
  referrer?: string;
  trackResponseAnalytics?: boolean;
}) {
  const isTimeseriesQuery = (eventView?.yAxis?.length ?? 0) > 0;
  const queryFunction = isTimeseriesQuery
    ? useWrappedDiscoverTimeseriesQuery
    : useWrappedDiscoverQuery;

  const {isReady: pageFiltersReady} = usePageFilters();

  if (eventView) {
    const newEventView = eventView.clone();
    const response = queryFunction<T>({
      eventView: newEventView,
      initialData,
      limit,
      // We always want to wait until the pageFilters are ready to prevent clobbering requests
      enabled: (enabled || enabled === undefined) && pageFiltersReady,
      referrer,
      cursor,
      allowAggregateConditions,
      samplingMode: queryExtras?.samplingMode,
    });

    if (trackResponseAnalytics) {
      TrackResponse(eventView, response);
    }

    return response;
  }

  throw new Error('eventView argument must be defined when Starfish useDiscover is true');
}

export function useWrappedDiscoverTimeseriesQuery<T>({
  eventView,
  enabled,
  initialData,
  referrer,
  cursor,
  overriddenRoute,
  samplingMode,
}: {
  eventView: EventView;
  cursor?: string;
  enabled?: boolean;
  initialData?: any;
  overriddenRoute?: string;
  referrer?: string;
  samplingMode?: SamplingMode;
}) {
  const location = useLocation();
  const organization = useOrganization();
  const {isReady: pageFiltersReady} = usePageFilters();

  const usesRelativeDateRange =
    !defined(eventView.start) &&
    !defined(eventView.end) &&
    defined(eventView.statsPeriod);

  const intervalInMilliseconds = eventView.interval
    ? intervalToMilliseconds(eventView.interval)
    : undefined;

  const result = useGenericDiscoverQuery<
    {
      data: any[];
      meta: MetaType;
    },
    DiscoverQueryProps
  >({
    route: overriddenRoute ?? 'events-stats',
    eventView,
    location,
    orgSlug: organization.slug,
    getRequestPayload: () => ({
      ...eventView.getEventsAPIPayload(location),
      yAxis: eventView.yAxis,
      topEvents: eventView.topEvents,
      excludeOther: 0,
      partial: 1,
      orderby: eventView.sorts?.[0] ? encodeSort(eventView.sorts?.[0]) : undefined,
      interval: eventView.interval,
      cursor,
      sampling:
        eventView.dataset === DiscoverDatasets.SPANS_EAP_RPC && samplingMode
          ? samplingMode
          : undefined,
    }),
    options: {
      enabled: enabled && pageFiltersReady,
      refetchOnWindowFocus: false,
      retry: shouldRetryHandler,
      retryDelay: getRetryDelay,
      staleTime:
        usesRelativeDateRange &&
        defined(intervalInMilliseconds) &&
        intervalInMilliseconds !== 0
          ? intervalInMilliseconds
          : Infinity,
    },
    referrer,
  });

  const isFetchingOrLoading = result.isPending || result.isFetching;
  const defaultData = initialData ?? undefined;

  const data: T = isFetchingOrLoading
    ? defaultData
    : processDiscoverTimeseriesResult(result.data, eventView);

  const pageLinks = result.response?.getResponseHeader('Link') ?? undefined;

  return {
    ...result,
    pageLinks,
    data,
    meta: result.data?.meta,
  };
}

export function useWrappedDiscoverQuery<T>({
  eventView,
  initialData,
  enabled,
  referrer,
  limit,
  cursor,
  noPagination,
  allowAggregateConditions,
  samplingMode,
}: {
  eventView: EventView;
  allowAggregateConditions?: boolean;
  cursor?: string;
  enabled?: boolean;
  initialData?: T;
  limit?: number;
  noPagination?: boolean;
  referrer?: string;
  samplingMode?: SamplingMode;
}) {
  const location = useLocation();
  const organization = useOrganization();
  const {isReady: pageFiltersReady} = usePageFilters();

  const queryExtras: Record<string, string> = {};
  if (eventView.dataset === DiscoverDatasets.SPANS_EAP_RPC && samplingMode) {
    queryExtras.sampling = samplingMode;
  }

  if (allowAggregateConditions !== undefined) {
    queryExtras.allowAggregateConditions = allowAggregateConditions ? '1' : '0';
  }

  const usesRelativeDateRange =
    !defined(eventView.start) &&
    !defined(eventView.end) &&
    defined(eventView.statsPeriod);

  const staleTimeForRelativePeriod = getStaleTimeForRelativePeriodTable(
    eventView.statsPeriod
  );

  const result = useDiscoverQuery({
    eventView,
    orgSlug: organization.slug,
    location,
    referrer,
    cursor,
    limit,
    options: {
      enabled: enabled && pageFiltersReady, // TODO this has a bug: if enabled is undefined, this short-circuits to undefined, which becomes true, regardless of pageFiltersReady
      refetchOnWindowFocus: false,
      retry: shouldRetryHandler,
      retryDelay: getRetryDelay,
      staleTime: usesRelativeDateRange ? staleTimeForRelativePeriod : Infinity,
    },
    queryExtras,
    noPagination,
  });

  // TODO: useDiscoverQuery incorrectly states that it returns MetaType, but it
  // does not!
  const meta = result.data?.meta as EventsMetaType | undefined;

  const data =
    result.isPending && initialData ? initialData : (result.data?.data as T | undefined);

  return {
    ...result,
    data,
    meta,
  };
}

type Interval = {interval: string; group?: string};

function processDiscoverTimeseriesResult(
  result: TableData | undefined,
  eventView: EventView
) {
  if (!result) {
    return undefined;
  }

  if (!eventView.yAxis) {
    return [];
  }

  const firstYAxis =
    typeof eventView.yAxis === 'string' ? eventView.yAxis : eventView.yAxis[0]!;

  if (result.data) {
    // Result data only returned one series. This means there was only only one yAxis requested, and no sub-series. Iterate the data, and return the result
    return processSingleDiscoverTimeseriesResult(result, firstYAxis).map(data => ({
      interval: moment(parseInt(data.interval, 10) * 1000).format(DATE_FORMAT),
      // @ts-expect-error TS(7053): Element implicitly has an 'any' type because expre... Remove this comment to see the full error message
      [firstYAxis]: data[firstYAxis],
      group: data.group,
    }));
  }

  let intervals = [] as Interval[];

  // Result data had more than one series, grouped by a key. This means either multiple yAxes were requested _or_ a top-N query was set. Iterate the keys, and construct a series for each one.
  Object.keys(result).forEach(key => {
    // Each key has just one timeseries. Either this is a simple multi-axis query, or a top-N query with just one axis
    // @ts-expect-error TS(7053): Element implicitly has an 'any' type because expre... Remove this comment to see the full error message
    if (result[key].data) {
      intervals = mergeIntervals(
        intervals,
        // @ts-expect-error TS(7053): Element implicitly has an 'any' type because expre... Remove this comment to see the full error message
        processSingleDiscoverTimeseriesResult(result[key], key)
      );
    } else {
      // Each key has more than one timeseries. This is a multi-axis top-N query. Iterate each series, but this time set both the key _and_ the group
      // @ts-expect-error TS(7053): Element implicitly has an 'any' type because expre... Remove this comment to see the full error message
      Object.keys(result[key]).forEach(innerKey => {
        if (innerKey !== 'order') {
          // `order` is a special value, each series has it in a multi-series query
          intervals = mergeIntervals(
            intervals,
            // @ts-expect-error TS(7053): Element implicitly has an 'any' type because expre... Remove this comment to see the full error message
            processSingleDiscoverTimeseriesResult(result[key][innerKey], innerKey, key)
          );
        }
      });
    }
  });

  const processed = intervals.map(interval => ({
    ...interval,
    interval: moment(parseInt(interval.interval, 10) * 1000).format(DATE_FORMAT),
  }));

  return processed;
}

function processSingleDiscoverTimeseriesResult(result: any, key: string, group?: string) {
  const intervals = [] as Interval[];

  // @ts-expect-error TS(7031): Binding element 'timestamp' implicitly has an 'any... Remove this comment to see the full error message
  result.data.forEach(([timestamp, [{count: value}]]) => {
    const existingInterval = intervals.find(
      interval =>
        interval.interval === timestamp && (group ? interval.group === group : true)
    );

    if (existingInterval) {
      // @ts-expect-error TS(7053): Element implicitly has an 'any' type because expre... Remove this comment to see the full error message
      existingInterval[key] = value;
      return;
    }

    intervals.push({
      interval: timestamp,
      [key]: value,
      group,
    });
  });

  return intervals;
}

function mergeIntervals(first: Interval[], second: Interval[]) {
  const target: Interval[] = JSON.parse(JSON.stringify(first));

  second.forEach(({interval: timestamp, group, ...rest}) => {
    const existingInterval = target.find(
      interval =>
        interval.interval === timestamp && (group ? interval.group === group : true)
    );

    if (existingInterval) {
      Object.keys(rest).forEach(key => {
        // @ts-expect-error TS(7053): Element implicitly has an 'any' type because expre... Remove this comment to see the full error message
        existingInterval[key] = rest[key];
      });

      return;
    }

    target.push({interval: timestamp, group, ...rest});
  });
  return target;
}

function getStaleTimeForRelativePeriodTable(statsPeriod: string | undefined) {
  if (!defined(statsPeriod)) {
    return Infinity;
  }
  const periodInMs = intervalToMilliseconds(statsPeriod);

  if (periodInMs <= SEVEN_DAYS) {
    return 0;
  }

  if (periodInMs <= FOURTEEN_DAYS) {
    return 10 * 1000;
  }

  if (periodInMs <= THIRTY_DAYS) {
    return 30 * 1000;
  }

  if (periodInMs <= SIXTY_DAYS) {
    return 60 * 1000;
  }

  return 5 * 60 * 1000;
}
