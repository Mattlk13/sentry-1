import 'echarts/lib/component/grid';
import 'echarts/lib/component/graphic';
import 'echarts/lib/component/toolbox';
import 'echarts/lib/component/brush';
import 'zrender/lib/svg/svg';

import {useId, useMemo} from 'react';
import type {Theme} from '@emotion/react';
import {css, Global, useTheme} from '@emotion/react';
import styled from '@emotion/styled';
import type {
  AxisPointerComponentOption,
  ECharts,
  EChartsOption,
  GridComponentOption,
  LegendComponentOption,
  LineSeriesOption,
  SeriesOption,
  TooltipComponentFormatterCallbackParams,
  TooltipComponentOption,
  VisualMapComponentOption,
  XAXisComponentOption,
  YAXisComponentOption,
} from 'echarts';
import {AriaComponent} from 'echarts/components';
import * as echarts from 'echarts/core';
import type {CallbackDataParams} from 'echarts/types/dist/shared';
import ReactEchartsCore from 'echarts-for-react/lib/core';

import MarkLine from 'sentry/components/charts/components/markLine';
import {space} from 'sentry/styles/space';
import type {
  EChartBrushEndHandler,
  EChartBrushSelectedHandler,
  EChartBrushStartHandler,
  EChartChartReadyHandler,
  EChartClickHandler,
  EChartDataZoomHandler,
  EChartDownplayHandler,
  EChartEventHandler,
  EChartFinishedHandler,
  EChartHighlightHandler,
  EChartMouseOutHandler,
  EChartMouseOverHandler,
  EChartRenderedHandler,
  EChartRestoreHandler,
  Series,
} from 'sentry/types/echarts';
import {defined} from 'sentry/utils';
import {isChonkTheme} from 'sentry/utils/theme/withChonk';

import Grid from './components/grid';
import Legend from './components/legend';
import {
  CHART_TOOLTIP_VIEWPORT_OFFSET,
  computeChartTooltip,
  type TooltipSubLabel,
} from './components/tooltip';
import XAxis from './components/xAxis';
import YAxis from './components/yAxis';
import LineSeries from './series/lineSeries';
import {
  computeEchartsAriaLabels,
  getDiffInMinutes,
  getDimensionValue,
  lightenHexToRgb,
} from './utils';

// TODO(ts): What is the series type? EChartOption.Series's data cannot have
// `onClick` since it's typically an array.
//
// Handle series item clicks (e.g. Releases mark line or a single series
// item) This is different than when you hover over an "axis" line on a chart
// (e.g.  if there are 2 series for an axis and you're not directly hovered
// over an item)
//
// Calls "onClick" inside of series data
const handleClick = (clickSeries: any, instance: ECharts) => {
  if (clickSeries.data) {
    clickSeries.data.onClick?.(clickSeries, instance);
  }
};

echarts.use(AriaComponent);

type ReactEchartProps = React.ComponentProps<typeof ReactEchartsCore>;
type ReactEChartOpts = NonNullable<ReactEchartProps['opts']>;

/**
 * Used for some properties that can be truncated
 */
type Truncateable = {
  /**
   * Truncate the label / value some number of characters.
   * If true is passed, it will use truncate based on a default length.
   */
  truncate?: number | boolean;
};

export interface TooltipOption
  extends Omit<TooltipComponentOption, 'valueFormatter'>,
    Truncateable {
  filter?: (value: number, seriesParam: TooltipComponentOption['formatter']) => boolean;
  formatAxisLabel?: (
    value: number,
    isTimestamp: boolean,
    utc: boolean,
    showTimeInTooltip: boolean,
    addSecondsToTimeFormat: boolean,
    bucketSize: number | undefined,
    seriesParamsOrParam: TooltipComponentFormatterCallbackParams
  ) => string;
  markerFormatter?: (marker: string, label?: string) => string;
  nameFormatter?: (name: string, seriesParams?: CallbackDataParams) => string;
  /**
   * If true does not display sublabels with a value of 0.
   */
  skipZeroValuedSubLabels?: boolean;
  /**
   * Array containing data that is used to display indented sublabels.
   */
  subLabels?: TooltipSubLabel[];
  valueFormatter?: (
    value: number,
    label?: string,
    seriesParams?: CallbackDataParams
  ) => string;
}

export interface BaseChartProps {
  /**
   * Additional Chart Series
   * This is to pass series to BaseChart bypassing the wrappers like LineChart, AreaChart etc.
   */
  additionalSeries?: SeriesOption[];
  /**
   * If true, ignores height value and auto-scales chart to fit container height.
   */
  autoHeightResize?: boolean;
  /**
   * Axis pointer options
   */
  axisPointer?: AxisPointerComponentOption;
  /**
   * ECharts Brush options
   */
  brush?: EChartsOption['brush'];
  /**
   * Bucket size to display time range in chart tooltip
   */
  bucketSize?: number;
  /**
   * Array of color codes to use in charts. May also take a function which is
   * provided with the current theme
   */
  colors?:
    | string[]
    | readonly string[]
    | ((
        theme: Theme
      ) => string[] | ReturnType<Theme['chart']['getColorPalette']> | undefined);
  'data-test-id'?: string;
  /**
   * DataZoom (allows for zooming of chart)
   */
  dataZoom?: EChartsOption['dataZoom'];
  devicePixelRatio?: ReactEChartOpts['devicePixelRatio'];
  /**
   * theme name
   * example theme: https://github.com/apache/incubator-echarts/blob/master/theme/dark.js
   */
  echartsTheme?: ReactEchartProps['theme'];
  /**
   * optional, used to determine how xAxis is formatted if `isGroupedByDate == true`
   */
  end?: Date;
  /**
   * Graphic options
   */
  graphic?: EChartsOption['graphic'];
  /**
   * ECharts Grid options. multiple grids allow multiple sub-graphs.
   */
  grid?: GridComponentOption | GridComponentOption[];
  /**
   * Chart height
   */
  height?: ReactEChartOpts['height'];

  /**
   * If data is grouped by date; then apply default date formatting to x-axis
   * and tooltips.
   */
  isGroupedByDate?: boolean;
  /**
   * states whether not to update chart immediately
   */
  lazyUpdate?: boolean;
  /**
   * Chart legend
   */
  legend?: LegendComponentOption & Truncateable;
  /**
   * optional, threshold in minutes used to add seconds to the xAxis datetime format if `isGroupedByDate == true`
   */
  minutesThresholdToDisplaySeconds?: number;
  /**
   * states whether or not to merge with previous `option`
   */
  notMerge?: boolean;
  onBrushEnd?: EChartBrushEndHandler;
  onBrushSelected?: EChartBrushSelectedHandler;
  onBrushStart?: EChartBrushStartHandler;
  onChartReady?: EChartChartReadyHandler;
  onClick?: EChartClickHandler;
  onDataZoom?: EChartDataZoomHandler;
  onDownplay?: EChartDownplayHandler;
  onFinished?: EChartFinishedHandler;
  onHighlight?: EChartHighlightHandler;
  onLegendSelectChanged?: EChartEventHandler<{
    name: string;
    selected: Record<string, boolean>;
    type: 'legendselectchanged';
  }>;
  onMouseOut?: EChartMouseOutHandler;
  onMouseOver?: EChartMouseOverHandler;
  onRendered?: EChartRenderedHandler;
  /**
   * One example of when this is called is restoring chart from zoom levels
   */
  onRestore?: EChartRestoreHandler;
  options?: EChartsOption;
  /**
   * optional, used to determine how xAxis is formatted if `isGroupedByDate == true`
   */
  period?: string | null;
  /**
   * Custom chart props that are implemented by us (and not a feature of eCharts)
   *
   * Display previous period as a LineSeries
   */
  previousPeriod?: Series[];
  ref?: React.Ref<ReactEchartsCore>;
  /**
   * Use `canvas` when dealing with large datasets
   * See: https://ecomfe.github.io/echarts-doc/public/en/tutorial.html#Render%20by%20Canvas%20or%20SVG
   */
  renderer?: ReactEChartOpts['renderer'];
  /**
   * Chart Series
   * This is different than the interface to higher level charts, these need to
   * be an array of ECharts "Series" components.
   */
  series?: SeriesOption[];
  /**
   * Format timestamp with date AND time
   */
  showTimeInTooltip?: boolean;
  /**
   * optional, used to determine how xAxis is formatted if `isGroupedByDate == true`
   */
  start?: Date;
  /**
   * Inline styles
   */
  style?: React.CSSProperties;
  /**
   * Toolbox options
   */
  toolBox?: EChartsOption['toolbox'];
  /**
   * Tooltip options. Pass `null` to disable tooltip.
   */
  tooltip?: TooltipOption | null;
  /**
   * If true and there's only one datapoint in series.data, we show a bar chart to increase the visibility.
   * Especially useful with line / area charts, because you can't draw line with single data point and one alone point is hard to spot.
   */
  transformSinglePointToBar?: boolean;
  /**
   * If true and there's only one datapoint in series.data, we show a horizontal line to increase the visibility
   * Similarly to single point bar in area charts a flat line for line charts makes it easy to spot the single data point.
   */
  transformSinglePointToLine?: boolean;
  /**
   * Use multiline date formatting for xAxis if grouped by date
   */
  useMultilineDate?: boolean;
  /**
   * Use short date formatting for xAxis
   */
  useShortDate?: boolean;
  /**
   * Formats dates as UTC?
   */
  utc?: boolean;
  /**
   * ECharts Visual Map Options.
   */
  visualMap?: VisualMapComponentOption | VisualMapComponentOption[];
  /**
   * Chart width
   */
  width?: ReactEChartOpts['width'];
  /**
   * Pass `true` to have 2 x-axes with default properties.  Can pass an array
   * of multiple objects to customize xAxis properties
   */
  xAxes?: true | Array<BaseChartProps['xAxis']>;
  /**
   * Must be explicitly `null` to disable xAxis
   *
   * Additionally a `truncate` option
   */
  xAxis?: (XAXisComponentOption & Truncateable) | null;

  /**
   * Pass `true` to have 2 y-axes with default properties. Can pass an array of
   * objects to customize yAxis properties
   */
  yAxes?: true | Array<BaseChartProps['yAxis']>;

  /**
   * Must be explicitly `null` to disable yAxis
   */
  yAxis?: YAXisComponentOption | null;
}

const DEFAULT_CHART_READY = () => {};
const DEFAULT_OPTIONS = {};
const DEFAULT_SERIES: SeriesOption[] = [];
const DEFAULT_ADDITIONAL_SERIES: LineSeriesOption[] = [];
const DEFAULT_Y_AXIS = {};
const DEFAULT_X_AXIS = {};

function BaseChart({
  brush,
  colors,
  grid,
  tooltip,
  legend,
  dataZoom,
  toolBox,
  graphic,
  axisPointer,
  previousPeriod,
  echartsTheme,
  devicePixelRatio,

  minutesThresholdToDisplaySeconds,
  showTimeInTooltip,
  useShortDate,
  useMultilineDate,
  start,
  end,
  period,
  utc,
  yAxes,
  xAxes,

  style,
  ref,

  onClick,
  onLegendSelectChanged,
  onHighlight,
  onDownplay,
  onMouseOut,
  onMouseOver,
  onDataZoom,
  onRestore,
  onFinished,
  onRendered,
  onBrushStart,
  onBrushEnd,
  onBrushSelected,

  options = DEFAULT_OPTIONS,
  series = DEFAULT_SERIES,
  additionalSeries = DEFAULT_ADDITIONAL_SERIES,
  yAxis = DEFAULT_Y_AXIS,
  xAxis = DEFAULT_X_AXIS,

  autoHeightResize = false,
  height = 200,
  width,
  renderer = 'svg',
  notMerge = true,
  lazyUpdate = false,
  isGroupedByDate = false,
  transformSinglePointToBar = false,
  transformSinglePointToLine = false,
  onChartReady = DEFAULT_CHART_READY,
  'data-test-id': dataTestId,
}: BaseChartProps) {
  const theme = useTheme();

  const resolveColors =
    colors === undefined ? null : typeof colors === 'function' ? colors(theme) : colors;

  const color =
    resolveColors ||
    (series.length
      ? theme.chart.getColorPalette(series.length)
      : theme.chart.getColorPalette(theme.chart.colors.length));

  const resolvedSeries = useMemo(() => {
    const previousPeriodColors =
      (previousPeriod?.length ?? 0) > 1 ? lightenHexToRgb(color) : undefined;

    const hasSinglePoints = (series as LineSeriesOption[] | undefined)?.every(
      s => Array.isArray(s.data) && s.data.length <= 1
    );

    const transformedSeries =
      (hasSinglePoints && transformSinglePointToBar
        ? (series as LineSeriesOption[] | undefined)?.map(s => ({
            ...s,
            type: 'bar',
            barWidth: 40,
            barGap: 0,
            itemStyle: {...s.areaStyle},
          }))
        : hasSinglePoints && transformSinglePointToLine
          ? (series as LineSeriesOption[] | undefined)?.map(s => ({
              ...s,
              type: 'line',
              itemStyle: {...s.lineStyle},
              markLine:
                (s?.data?.[0] as any)?.[1] === undefined
                  ? undefined
                  : MarkLine({
                      silent: true,
                      lineStyle: {
                        type: 'solid',
                        width: 1.5,
                      },
                      data: [{yAxis: (s?.data?.[0] as any)?.[1]}],
                      label: {
                        show: false,
                      },
                    }),
            }))
          : series) ?? [];

    const transformedPreviousPeriod =
      previousPeriod?.map((previous, seriesIndex) =>
        LineSeries({
          name: previous.seriesName,
          data: previous.data.map(({name, value}) => [name, value]),
          lineStyle: {
            color: previousPeriodColors
              ? previousPeriodColors[seriesIndex]
              : isChonkTheme(theme)
                ? theme.colors.gray400
                : theme.gray200,
            type: 'dotted',
          },
          itemStyle: {
            color: previousPeriodColors
              ? previousPeriodColors[seriesIndex]
              : isChonkTheme(theme)
                ? theme.colors.gray400
                : theme.gray200,
          },
          stack: 'previous',
          animation: false,
        })
      ) ?? [];

    return previousPeriod
      ? transformedSeries.concat(transformedPreviousPeriod, additionalSeries)
      : transformedSeries.concat(additionalSeries);
  }, [
    series,
    color,
    transformSinglePointToBar,
    transformSinglePointToLine,
    previousPeriod,
    additionalSeries,
    theme,
  ]);

  /**
   * If true seconds will be added to the time format in the tooltips and chart xAxis
   */
  const addSecondsToTimeFormat =
    isGroupedByDate && defined(minutesThresholdToDisplaySeconds)
      ? getDiffInMinutes({start, end, period}) <= minutesThresholdToDisplaySeconds
      : false;

  const isTooltipPortalled = tooltip?.appendToBody;
  const chartId = useId();

  const chartOption = useMemo(() => {
    const seriesData =
      Array.isArray(series?.[0]?.data) && series[0].data.length > 1
        ? series[0].data
        : undefined;

    const bucketSize = seriesData ? seriesData[1][0] - seriesData[0][0] : undefined;
    const tooltipOrNone =
      tooltip === null
        ? undefined
        : computeChartTooltip(
            {
              showTimeInTooltip,
              isGroupedByDate,
              addSecondsToTimeFormat,
              utc,
              bucketSize,
              chartId: isTooltipPortalled ? chartId : undefined,
              ...tooltip,
              className: isTooltipPortalled
                ? `${tooltip?.className ?? ''} chart-tooltip-portal`
                : tooltip?.className,
            },
            theme
          );

    const aria = computeEchartsAriaLabels(
      {series: resolvedSeries, useUTC: utc},
      isGroupedByDate
    );
    const defaultAxesProps = {theme};

    const yAxisOrCustom = yAxes
      ? Array.isArray(yAxes)
        ? yAxes.map(axis => YAxis({...axis, theme}))
        : [YAxis(defaultAxesProps), YAxis(defaultAxesProps)]
      : yAxis === null
        ? undefined
        : YAxis({theme, ...yAxis});

    const xAxisOrCustom = xAxes
      ? Array.isArray(xAxes)
        ? xAxes.map(axis =>
            XAxis({
              ...axis,
              theme,
              useShortDate,
              useMultilineDate,
              start,
              end,
              period,
              isGroupedByDate,
              addSecondsToTimeFormat,
              utc,
            })
          )
        : [XAxis(defaultAxesProps), XAxis(defaultAxesProps)]
      : xAxis === null
        ? undefined
        : XAxis({
            ...xAxis,
            theme,
            useShortDate,
            useMultilineDate,
            start,
            end,
            period,
            isGroupedByDate,
            addSecondsToTimeFormat,
            utc,
          });

    return {
      ...options,
      useUTC: utc,
      color,
      grid: Array.isArray(grid) ? grid.map(Grid) : Grid(grid),
      tooltip: tooltipOrNone,
      legend: legend ? Legend({theme, ...legend}) : undefined,
      yAxis: yAxisOrCustom,
      xAxis: xAxisOrCustom,
      series: resolvedSeries,
      toolbox: toolBox,
      axisPointer,
      dataZoom,
      graphic,
      aria,
      brush,
    };
  }, [
    chartId,
    color,
    resolvedSeries,
    isTooltipPortalled,
    theme,
    series,
    tooltip,
    showTimeInTooltip,
    addSecondsToTimeFormat,
    options,
    utc,
    grid,
    legend,
    toolBox,
    brush,
    axisPointer,
    dataZoom,
    graphic,
    isGroupedByDate,
    useShortDate,
    useMultilineDate,
    start,
    end,
    period,
    xAxis,
    xAxes,
    yAxes,
    yAxis,
  ]);

  // XXX(epurkhiser): Echarts can become unhappy if one of these event handlers
  // causes the chart to re-render and be passed a whole different instance of
  // event handlers.
  //
  // We use React.useMemo to keep the value across renders
  //
  const eventsMap = useMemo(
    () =>
      ({
        click: (props: any, instance: ECharts) => {
          handleClick(props, instance);
          onClick?.(props, instance);
        },

        highlight: (props: any, instance: ECharts) => onHighlight?.(props, instance),
        downplay: (props: any, instance: ECharts) => onDownplay?.(props, instance),
        mouseout: (props: any, instance: ECharts) => onMouseOut?.(props, instance),
        mouseover: (props: any, instance: ECharts) => onMouseOver?.(props, instance),
        datazoom: (props: any, instance: ECharts) => onDataZoom?.(props, instance),
        restore: (props: any, instance: ECharts) => onRestore?.(props, instance),
        finished: (props: any, instance: ECharts) => onFinished?.(props, instance),
        rendered: (props: any, instance: ECharts) => onRendered?.(props, instance),

        legendselectchanged: (props: any, instance: ECharts) =>
          onLegendSelectChanged?.(props, instance),

        brush: (props: any, instance: ECharts) => onBrushStart?.(props, instance),
        brushend: (props: any, instance: ECharts) => onBrushEnd?.(props, instance),

        brushselected: (props: any, instance: ECharts) =>
          onBrushSelected?.(props, instance),
      }) as ReactEchartProps['onEvents'],
    [
      onClick,
      onHighlight,
      onDownplay,
      onLegendSelectChanged,
      onMouseOut,
      onMouseOver,
      onDataZoom,
      onRestore,
      onFinished,
      onRendered,
      onBrushStart,
      onBrushEnd,
      onBrushSelected,
    ]
  );

  const coreOptions = useMemo(() => {
    return {
      height: autoHeightResize ? undefined : height,
      width,
      renderer,
      devicePixelRatio,
    };
  }, [autoHeightResize, height, width, renderer, devicePixelRatio]);

  const chartStyles = useMemo(() => {
    return {
      height: autoHeightResize ? '100%' : getDimensionValue(height),
      width: getDimensionValue(width),
      ...style,
    };
  }, [style, autoHeightResize, height, width]);

  return (
    <ChartContainer
      id={isTooltipPortalled ? chartId : undefined}
      autoHeightResize={autoHeightResize}
      data-test-id={dataTestId}
    >
      {isTooltipPortalled && <Global styles={getPortalledTooltipStyles({theme})} />}
      <ReactEchartsCore
        ref={ref}
        echarts={echarts}
        notMerge={notMerge}
        lazyUpdate={lazyUpdate}
        theme={echartsTheme}
        onChartReady={onChartReady}
        onEvents={eventsMap}
        style={chartStyles}
        opts={coreOptions}
        option={chartOption}
      />
    </ChartContainer>
  );
}

// Tooltip styles shared for regular and portalled tooltips
export const getTooltipStyles = (p: {theme: Theme}) => css`
  /* Tooltip styling */
  .tooltip-series,
  .tooltip-footer {
    color: ${p.theme.subText};
    font-family: ${p.theme.text.family};
    font-variant-numeric: tabular-nums;
    padding: ${space(1)} ${space(2)};
    border-radius: ${p.theme.borderRadius} ${p.theme.borderRadius} 0 0;
    cursor: pointer;
    font-size: ${p.theme.fontSize.sm};
  }
  .tooltip-release.tooltip-series > div,
  .tooltip-release.tooltip-footer {
    justify-content: center;
  }
  .tooltip-release.tooltip-series {
    color: ${p.theme.textColor};
  }
  .tooltip-release-timerange {
    font-size: ${p.theme.fontSize.xs};
    color: ${p.theme.textColor};
  }
  .tooltip-series {
    border-bottom: none;
    max-width: calc(100vw - 2 * ${CHART_TOOLTIP_VIEWPORT_OFFSET}px);
  }
  .tooltip-series-solo {
    border-radius: ${p.theme.borderRadius};
  }
  .tooltip-label {
    margin-right: ${space(1)};
    ${p.theme.overflowEllipsis};
  }
  .tooltip-label strong {
    font-weight: ${p.theme.fontWeight.normal};
    color: ${p.theme.textColor};
  }
  .tooltip-label-value {
    color: ${p.theme.textColor};
  }
  .tooltip-label-indent {
    margin-left: 18px;
  }
  .tooltip-series > div {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
  }
  .tooltip-label-align-start {
    display: flex;
    justify-content: flex-start;
    align-items: baseline;
  }
  .tooltip-code-no-margin {
    padding-left: 0;
    margin-left: 0;
    color: ${p.theme.subText};
  }
  .tooltip-footer {
    border-top: solid 1px ${p.theme.innerBorder};
    text-align: center;
    position: relative;
    width: auto;
    border-radius: 0 0 ${p.theme.borderRadius} ${p.theme.borderRadius};
    display: flex;
    justify-content: space-between;
    gap: ${space(3)};
  }

  .tooltip-footer-centered {
    justify-content: center;
    gap: 0;
  }

  .tooltip-arrow {
    &.arrow-top {
      bottom: 100%;
      top: auto;
      border-bottom: 8px solid ${p.theme.backgroundElevated};
      border-top: none;
      &:before {
        border-top: none;
        border-bottom: 8px solid ${p.theme.translucentBorder};
        bottom: -7px;
        top: auto;
      }
    }

    top: 100%;
    left: 50%;
    position: absolute;
    pointer-events: none;
    border-left: 8px solid transparent;
    border-right: 8px solid transparent;
    border-top: 8px solid ${p.theme.backgroundElevated};
    margin-left: -8px;
    &:before {
      border-left: 8px solid transparent;
      border-right: 8px solid transparent;
      border-top: 8px solid ${p.theme.translucentBorder};
      content: '';
      display: block;
      position: absolute;
      top: -7px;
      left: -8px;
      z-index: -1;
    }
  }

  /* Tooltip description styling */
  .tooltip-description {
    color: ${p.theme.white};
    border-radius: ${p.theme.borderRadius};
    background: #000;
    opacity: 0.9;
    padding: 5px 10px;
    position: relative;
    font-weight: ${p.theme.fontWeight.bold};
    font-size: ${p.theme.fontSize.sm};
    line-height: 1.4;
    font-family: ${p.theme.text.family};
    max-width: 230px;
    min-width: 230px;
    white-space: normal;
    text-align: center;
    :after {
      content: '';
      position: absolute;
      top: 100%;
      left: 50%;
      width: 0;
      height: 0;
      border-left: 5px solid transparent;
      border-right: 5px solid transparent;
      border-top: 5px solid #000;
      transform: translateX(-50%);
    }
  }
`;

// Contains styling for chart elements as we can't easily style those
// elements directly
const ChartContainer = styled('div')<{autoHeightResize: boolean}>`
  ${p => p.autoHeightResize && 'height: 100%;'}

  .echarts-for-react div:first-of-type {
    width: 100% !important;
  }

  .echarts-for-react text {
    font-variant-numeric: tabular-nums !important;
  }

  ${p => getTooltipStyles(p)}
`;

const getPortalledTooltipStyles = (p: {theme: Theme}) => css`
  .chart-tooltip-portal {
    ${getTooltipStyles(p)};
  }
`;

export default BaseChart;
