import {doEventsRequest} from 'sentry/actionCreators/events';
import type {Client} from 'sentry/api';
import type {PageFilters} from 'sentry/types/core';
import type {TagCollection} from 'sentry/types/group';
import type {
  EventsStats,
  GroupedMultiSeriesEventsStats,
  MultiSeriesEventsStats,
  Organization,
} from 'sentry/types/organization';
import {defined} from 'sentry/utils';
import type {CustomMeasurementCollection} from 'sentry/utils/customMeasurements/customMeasurements';
import type {EventsTableData, TableData} from 'sentry/utils/discover/discoverQuery';
import {
  getAggregations,
  type QueryFieldValue,
  SPAN_OP_BREAKDOWN_FIELDS,
  TRANSACTION_FIELDS,
  TRANSACTIONS_AGGREGATION_FUNCTIONS,
} from 'sentry/utils/discover/fields';
import type {
  DiscoverQueryExtras,
  DiscoverQueryRequestParams,
} from 'sentry/utils/discover/genericDiscoverQuery';
import {doDiscoverQuery} from 'sentry/utils/discover/genericDiscoverQuery';
import {DiscoverDatasets} from 'sentry/utils/discover/types';
import {AggregationKey} from 'sentry/utils/fields';
import {getMeasurements} from 'sentry/utils/measurements/measurements';
import {MEPState} from 'sentry/utils/performance/contexts/metricsEnhancedSetting';
import {
  type OnDemandControlContext,
  shouldUseOnDemandMetrics,
} from 'sentry/utils/performance/contexts/onDemandControl';
import {getSeriesRequestData} from 'sentry/views/dashboards/datasetConfig/utils/getSeriesRequestData';
import type {Widget, WidgetQuery} from 'sentry/views/dashboards/types';
import {DisplayType} from 'sentry/views/dashboards/types';
import {eventViewFromWidget} from 'sentry/views/dashboards/utils';
import {transformEventsResponseToSeries} from 'sentry/views/dashboards/utils/transformEventsResponseToSeries';
import {EventsSearchBar} from 'sentry/views/dashboards/widgetBuilder/buildSteps/filterResultsStep/eventsSearchBar';
import {FieldValueKind} from 'sentry/views/discover/table/types';
import {generateFieldOptions} from 'sentry/views/discover/utils';

import {type DatasetConfig, handleOrderByReset} from './base';
import {
  doOnDemandMetricsRequest,
  filterAggregateParams,
  filterSeriesSortOptions,
  filterYAxisAggregateParams,
  filterYAxisOptions,
  getCustomEventsFieldRenderer,
  getTableSortOptions,
  getTimeseriesSortOptions,
  transformEventsResponseToTable,
} from './errorsAndTransactions';

const DEFAULT_WIDGET_QUERY: WidgetQuery = {
  name: '',
  fields: ['count_unique(user)'],
  columns: [],
  fieldAliases: [],
  aggregates: ['count_unique(user)'],
  conditions: '',
  orderby: '-count_unique(user)',
};

const DEFAULT_FIELD: QueryFieldValue = {
  function: ['count_unique', 'user', undefined, undefined],
  kind: FieldValueKind.FUNCTION,
};

export const TransactionsConfig: DatasetConfig<
  EventsStats | MultiSeriesEventsStats | GroupedMultiSeriesEventsStats,
  TableData | EventsTableData
> = {
  defaultField: DEFAULT_FIELD,
  defaultWidgetQuery: DEFAULT_WIDGET_QUERY,
  enableEquations: true,
  getCustomFieldRenderer: getCustomEventsFieldRenderer,
  SearchBar: EventsSearchBar,
  filterSeriesSortOptions,
  filterYAxisAggregateParams,
  filterYAxisOptions,
  getTableFieldOptions: getEventsTableFieldOptions,
  getTimeseriesSortOptions,
  getTableSortOptions,
  getGroupByFieldOptions: getEventsTableFieldOptions,
  handleOrderByReset,
  supportedDisplayTypes: [
    DisplayType.AREA,
    DisplayType.BAR,
    DisplayType.BIG_NUMBER,
    DisplayType.LINE,
    DisplayType.TABLE,
    DisplayType.TOP_N,
  ],
  getTableRequest: (
    api: Client,
    widget: Widget,
    query: WidgetQuery,
    organization: Organization,
    pageFilters: PageFilters,
    onDemandControlContext?: OnDemandControlContext,
    limit?: number,
    cursor?: string,
    referrer?: string,
    mepSetting?: MEPState | null
  ) => {
    const useOnDemandMetrics = shouldUseOnDemandMetrics(
      organization,
      widget,
      onDemandControlContext
    );
    const queryExtras = {
      useOnDemandMetrics,
      onDemandType: 'dynamic_query',
    };
    return getEventsRequest(
      api,
      query,
      organization,
      pageFilters,
      limit,
      cursor,
      referrer,
      mepSetting,
      queryExtras
    );
  },
  getSeriesRequest: getEventsSeriesRequest,
  transformSeries: transformEventsResponseToSeries,
  transformTable: transformEventsResponseToTable,
  filterAggregateParams,
};

function getEventsTableFieldOptions(
  organization: Organization,
  tags?: TagCollection,
  customMeasurements?: CustomMeasurementCollection
) {
  const measurements = getMeasurements();
  const aggregates = getAggregations(DiscoverDatasets.TRANSACTIONS);

  return generateFieldOptions({
    organization,
    tagKeys: Object.values(tags ?? {}).map(({key}) => key),
    measurementKeys: Object.values(measurements).map(({key}) => key),
    spanOperationBreakdownKeys: SPAN_OP_BREAKDOWN_FIELDS,
    customMeasurements: Object.values(customMeasurements ?? {}).map(
      ({key, functions}) => ({
        key,
        functions,
      })
    ),
    aggregations: Object.keys(aggregates)
      .filter(key => TRANSACTIONS_AGGREGATION_FUNCTIONS.includes(key as AggregationKey))
      .reduce((obj, key) => {
        // @ts-expect-error TS(7053): Element implicitly has an 'any' type because expre... Remove this comment to see the full error message
        obj[key] = aggregates[key];
        return obj;
      }, {}),
    fieldKeys: TRANSACTION_FIELDS,
  });
}

function getEventsRequest(
  api: Client,
  query: WidgetQuery,
  organization: Organization,
  pageFilters: PageFilters,
  limit?: number,
  cursor?: string,
  referrer?: string,
  mepSetting?: MEPState | null,
  queryExtras?: DiscoverQueryExtras
) {
  const isMEPEnabled = defined(mepSetting) && mepSetting !== MEPState.TRANSACTIONS_ONLY;
  const url = `/organizations/${organization.slug}/events/`;

  // To generate the target url for TRACE ID links we always include a timestamp,
  // to speed up the trace endpoint. Adding timestamp for the non-aggregate case and
  // max(timestamp) for the aggregate case as fields, to accomodate this.
  if (
    query.aggregates.length &&
    query.columns.includes('trace') &&
    !query.aggregates.includes('max(timestamp)') &&
    !query.columns.includes('timestamp')
  ) {
    query.aggregates.push('max(timestamp)');
  } else if (query.columns.includes('trace') && !query.columns.includes('timestamp')) {
    query.columns.push('timestamp');
  }

  const eventView = eventViewFromWidget('', query, pageFilters);

  const params: DiscoverQueryRequestParams = {
    per_page: limit,
    cursor,
    referrer,
    dataset: isMEPEnabled
      ? DiscoverDatasets.METRICS_ENHANCED
      : DiscoverDatasets.TRANSACTIONS,
    ...queryExtras,
  };

  if (query.orderby) {
    params.sort = typeof query.orderby === 'string' ? [query.orderby] : query.orderby;
  }

  return doDiscoverQuery<EventsTableData>(
    api,
    url,
    {
      ...eventView.generateQueryStringObject(),
      ...params,
    },
    // Tries events request up to 3 times on rate limit
    {
      retry: {
        statusCodes: [429],
        tries: 3,
      },
    }
  );
}

function getEventsSeriesRequest(
  api: Client,
  widget: Widget,
  queryIndex: number,
  organization: Organization,
  pageFilters: PageFilters,
  onDemandControlContext?: OnDemandControlContext,
  referrer?: string,
  mepSetting?: MEPState | null
) {
  const isMEPEnabled = defined(mepSetting) && mepSetting !== MEPState.TRANSACTIONS_ONLY;

  const requestData = getSeriesRequestData(
    widget,
    queryIndex,
    organization,
    pageFilters,
    isMEPEnabled ? DiscoverDatasets.METRICS_ENHANCED : DiscoverDatasets.TRANSACTIONS,
    referrer
  );

  if (shouldUseOnDemandMetrics(organization, widget, onDemandControlContext)) {
    requestData.queryExtras = {
      ...requestData.queryExtras,
      ...{dataset: DiscoverDatasets.METRICS_ENHANCED},
    };
    return doOnDemandMetricsRequest(api, requestData, widget.widgetType);
  }

  return doEventsRequest<true>(api, requestData);
}
