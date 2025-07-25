import type {DO_NOT_USE_ChonkTheme, Theme} from '@emotion/react';

import {
  makeColorMapByApplicationFrame,
  makeColorMapByFrequency,
  makeColorMapByLibrary,
  makeColorMapByRecursion,
  makeColorMapBySymbolName,
  makeColorMapBySystemFrame,
  makeColorMapBySystemVsApplicationFrame,
  makeStackToColor,
} from 'sentry/utils/profiling/colors/utils';
import type {FlamegraphColorCodings} from 'sentry/utils/profiling/flamegraph/flamegraphStateProvider/reducers/flamegraphPreferences';
import type {FlamegraphFrame} from 'sentry/utils/profiling/flamegraphFrame';
import type {Frame} from 'sentry/utils/profiling/frame';
import {hexToColorChannels} from 'sentry/utils/profiling/gl/utils';
import {makeColorBucketTheme} from 'sentry/utils/profiling/speedscope';

const MONOSPACE_FONT = `ui-monospace, Menlo, Monaco, 'Cascadia Mono', 'Segoe UI Mono', 'Roboto Mono',
'Oxygen Mono', 'Ubuntu Monospace', 'Source Code Pro', 'Fira Mono', 'Droid Sans Mono',
'Courier New', monospace`;

// Luma chroma settings
export interface LCH {
  C_0: number;
  C_d: number;
  L_0: number;
  L_d: number;
}
// Color can be rgb or rgba. I want to probably eliminate rgb and just use rgba, but we would be allocating 25% more memory,
// and I'm not sure about the impact we'd need. There is a tradeoff between memory and runtime performance checks that I'll need to evaluate at some point.
export type ColorChannels = [number, number, number] | [number, number, number, number];

export type ColorMapFn = (
  frames: readonly FlamegraphFrame[],
  colorBucket: FlamegraphTheme['COLORS']['COLOR_BUCKET'],
  theme: FlamegraphTheme,
  sortByKey?: (a: FlamegraphFrame, b: FlamegraphFrame) => number
) => Map<FlamegraphFrame['frame']['key'], ColorChannels>;

export interface FlamegraphTheme {
  // @TODO, most colors are defined as strings, which is a mistake as we loose a lot of functionality and impose constraints.
  // They should instead be defined as arrays of numbers so we can use them with glsl and avoid unnecessary parsing
  COLORS: {
    BAR_LABEL_FONT_COLOR: string;
    BATTERY_CHART_COLORS: ColorChannels[];
    CHART_CURSOR_INDICATOR: string;
    CHART_LABEL_COLOR: string;
    COLOR_BUCKET: (t: number) => ColorChannels;
    COLOR_MAPS: Record<FlamegraphColorCodings[number], ColorMapFn>;
    CPU_CHART_COLORS: ColorChannels[];
    CURSOR_CROSSHAIR: string;
    DIFFERENTIAL_DECREASE: ColorChannels;
    DIFFERENTIAL_INCREASE: ColorChannels;
    FOCUSED_FRAME_BORDER_COLOR: string;
    FRAME_APPLICATION_COLOR: ColorChannels;
    FRAME_FALLBACK_COLOR: ColorChannels;
    FRAME_SYSTEM_COLOR: ColorChannels;
    GRID_FRAME_BACKGROUND_COLOR: string;
    GRID_LINE_COLOR: string;
    HIGHLIGHTED_LABEL_COLOR: string;
    HOVERED_FRAME_BORDER_COLOR: string;
    LABEL_FONT_COLOR: string;
    MEMORY_CHART_COLORS: ColorChannels[];
    MINIMAP_POSITION_OVERLAY_BORDER_COLOR: string;
    MINIMAP_POSITION_OVERLAY_COLOR: string;
    // Nice color picker for GLSL colors - https://keiwando.com/color-picker/
    SAMPLE_TICK_COLOR: ColorChannels;
    SEARCH_RESULT_FRAME_COLOR: string;
    SEARCH_RESULT_SPAN_COLOR: string;
    SELECTED_FRAME_BORDER_COLOR: string;
    SPAN_COLOR_BUCKET: (t: number) => ColorChannels;
    SPAN_FALLBACK_COLOR: [number, number, number, number];
    SPAN_FRAME_BORDER: string;
    SPAN_FRAME_LINE_PATTERN: string;
    SPAN_FRAME_LINE_PATTERN_BACKGROUND: string;
    STACK_TO_COLOR: (
      frames: readonly FlamegraphFrame[],
      colorMapFn: ColorMapFn,
      colorBucketFn: FlamegraphTheme['COLORS']['COLOR_BUCKET'],
      theme: FlamegraphTheme
    ) => {
      colorBuffer: number[];
      colorMap: Map<Frame['key'], ColorChannels>;
    };
    UI_FRAME_COLOR_FROZEN: ColorChannels;
    UI_FRAME_COLOR_SLOW: ColorChannels;
  };
  FONTS: {
    FONT: string;
    FRAME_FONT: string;
  };
  LCH: LCH;
  SIZES: {
    AGGREGATE_FLAMEGRAPH_DEPTH_OFFSET: number;
    BAR_FONT_SIZE: number;
    BAR_HEIGHT: number;
    BAR_PADDING: number;
    BATTERY_CHART_HEIGHT: number;
    CHART_PX_PADDING: number;
    CPU_CHART_HEIGHT: number;
    FLAMEGRAPH_DEPTH_OFFSET: number;
    GRID_LINE_WIDTH: number;
    HIGHLIGHTED_FRAME_BORDER_WIDTH: any;
    HOVERED_FRAME_BORDER_WIDTH: number;
    INTERNAL_SAMPLE_TICK_LINE_WIDTH: number;
    LABEL_FONT_PADDING: number;
    LABEL_FONT_SIZE: number;
    MAX_SPANS_HEIGHT: number;
    MEMORY_CHART_HEIGHT: number;
    METRICS_FONT_SIZE: number;
    MINIMAP_HEIGHT: number;
    MINIMAP_POSITION_OVERLAY_BORDER_WIDTH: number;
    SPANS_BAR_HEIGHT: number;
    SPANS_DEPTH_OFFSET: number;
    SPANS_FONT_SIZE: number;
    TIMELINE_HEIGHT: number;
    TIMELINE_LABEL_HEIGHT: number;
    TOOLTIP_FONT_SIZE: number;
    UI_FRAMES_HEIGHT: number;
  };
}

// Luma chroma settings for light theme
const LCH_LIGHT = {
  C_0: 0.25,
  C_d: 0.2,
  L_0: 0.8,
  L_d: 0.15,
};

// Luma chroma settings for dark theme
const LCH_DARK = {
  C_0: 0.2,
  C_d: 0.1,
  L_0: 0.2,
  L_d: 0.1,
};

const SPAN_LCH_LIGHT = {
  C_0: 0.3,
  C_d: 0.25,
  L_0: 0.8,
  L_d: 0.15,
};

const SPANS_LCH_DARK = {
  C_0: 0.3,
  C_d: 0.15,
  L_0: 0.2,
  L_d: 0.1,
};

const SIZES: FlamegraphTheme['SIZES'] = {
  AGGREGATE_FLAMEGRAPH_DEPTH_OFFSET: 4,
  BAR_FONT_SIZE: 11,
  BAR_HEIGHT: 20,
  BAR_PADDING: 4,
  BATTERY_CHART_HEIGHT: 80,
  FLAMEGRAPH_DEPTH_OFFSET: 12,
  HOVERED_FRAME_BORDER_WIDTH: 2,
  HIGHLIGHTED_FRAME_BORDER_WIDTH: 3,
  GRID_LINE_WIDTH: 2,
  INTERNAL_SAMPLE_TICK_LINE_WIDTH: 1,
  LABEL_FONT_PADDING: 6,
  LABEL_FONT_SIZE: 10,
  MINIMAP_HEIGHT: 100,
  CPU_CHART_HEIGHT: 80,
  MEMORY_CHART_HEIGHT: 80,
  MINIMAP_POSITION_OVERLAY_BORDER_WIDTH: 2,
  SPANS_BAR_HEIGHT: 20,
  SPANS_DEPTH_OFFSET: 3,
  SPANS_FONT_SIZE: 11,
  METRICS_FONT_SIZE: 9,
  MAX_SPANS_HEIGHT: 160,
  TIMELINE_HEIGHT: 20,
  TOOLTIP_FONT_SIZE: 12,
  TIMELINE_LABEL_HEIGHT: 20,
  UI_FRAMES_HEIGHT: 60,
  CHART_PX_PADDING: 30,
};

function makeFlamegraphFonts(
  theme: Theme | DO_NOT_USE_ChonkTheme
): FlamegraphTheme['FONTS'] {
  return {
    FONT: MONOSPACE_FONT,
    FRAME_FONT: theme.text.familyMono,
  };
}

/** Legacy theme definitions */
export function makeLightFlamegraphTheme(theme: Theme): FlamegraphTheme {
  const chartColors = theme.chart.getColorPalette(12);
  return {
    LCH: LCH_LIGHT,
    SIZES,
    FONTS: makeFlamegraphFonts(theme),
    COLORS: {
      BAR_LABEL_FONT_COLOR: '#000',
      BATTERY_CHART_COLORS: [[0.4, 0.56, 0.9, 0.65]],
      COLOR_BUCKET: makeColorBucketTheme(LCH_LIGHT),
      SPAN_COLOR_BUCKET: makeColorBucketTheme(SPAN_LCH_LIGHT, 140, 220),
      COLOR_MAPS: {
        'by symbol name': makeColorMapBySymbolName,
        'by system frame': makeColorMapBySystemFrame,
        'by application frame': makeColorMapByApplicationFrame,
        'by library': makeColorMapByLibrary,
        'by recursion': makeColorMapByRecursion,
        'by frequency': makeColorMapByFrequency,
        'by system vs application frame': makeColorMapBySystemVsApplicationFrame,
      },
      CPU_CHART_COLORS: chartColors.map(c => hexToColorChannels(c, 0.8)),
      MEMORY_CHART_COLORS: [
        hexToColorChannels(chartColors[2], 0.8),
        hexToColorChannels(chartColors[3], 0.8),
      ],
      CHART_CURSOR_INDICATOR: 'rgba(31,35,58,.75)',
      CHART_LABEL_COLOR: 'rgba(31,35,58,.75)',
      CURSOR_CROSSHAIR: '#bbbbbb',
      DIFFERENTIAL_DECREASE: [0.309, 0.2558, 0.78],
      DIFFERENTIAL_INCREASE: [0.84, 0.3, 0.33],
      FOCUSED_FRAME_BORDER_COLOR: theme.focus,
      FRAME_FALLBACK_COLOR: [0.5, 0.5, 0.6, 0.1],
      FRAME_APPLICATION_COLOR: [0.1, 0.1, 0.8, 0.2],
      FRAME_SYSTEM_COLOR: [0.7, 0.1, 0.1, 0.2],
      SPAN_FALLBACK_COLOR: [0, 0, 0, 0.1],
      GRID_FRAME_BACKGROUND_COLOR: 'rgb(250, 249, 251, 1)', // theme.backgroundSecondary
      GRID_LINE_COLOR: '#e5e7eb',
      HIGHLIGHTED_LABEL_COLOR: 'rgba(240, 240, 0, 1)',
      HOVERED_FRAME_BORDER_COLOR: 'rgba(0, 0, 0, 0.8)',
      LABEL_FONT_COLOR: '#1f233a',
      MINIMAP_POSITION_OVERLAY_BORDER_COLOR: 'rgba(0,0,0, 0.2)',
      MINIMAP_POSITION_OVERLAY_COLOR: 'rgba(0,0,0,0.1)',
      SAMPLE_TICK_COLOR: [255, 0, 0, 0.5],
      // Yellow 200
      UI_FRAME_COLOR_SLOW: [0.96, 0.69, 0.0, 0.55],
      // Red 200 but stronger opacity
      UI_FRAME_COLOR_FROZEN: [0.96, 0.329, 0.349, 0.8],
      SEARCH_RESULT_FRAME_COLOR: 'vec4(0.99, 0.70, 0.35, 1.0)',
      SEARCH_RESULT_SPAN_COLOR: '#fdb359',
      SELECTED_FRAME_BORDER_COLOR: theme.blue400,
      SPAN_FRAME_LINE_PATTERN: '#dedae3',
      SPAN_FRAME_LINE_PATTERN_BACKGROUND: '#f4f2f7',
      SPAN_FRAME_BORDER: 'rgba(200, 200, 200, 1)',
      STACK_TO_COLOR: makeStackToColor([0, 0, 0, 0.035]),
    },
  };
}

export function makeDarkFlamegraphTheme(theme: Theme): FlamegraphTheme {
  const chartColors = theme.chart.getColorPalette(12);
  return {
    LCH: LCH_DARK,
    SIZES,
    FONTS: makeFlamegraphFonts(theme),
    COLORS: {
      BAR_LABEL_FONT_COLOR: 'rgb(255 255 255 / 80%)',
      BATTERY_CHART_COLORS: [[0.4, 0.56, 0.9, 0.5]],
      COLOR_BUCKET: makeColorBucketTheme(LCH_DARK),
      SPAN_COLOR_BUCKET: makeColorBucketTheme(SPANS_LCH_DARK, 140, 220),
      COLOR_MAPS: {
        'by symbol name': makeColorMapBySymbolName,
        'by system frame': makeColorMapBySystemFrame,
        'by application frame': makeColorMapByApplicationFrame,
        'by library': makeColorMapByLibrary,
        'by recursion': makeColorMapByRecursion,
        'by frequency': makeColorMapByFrequency,
        'by system vs application frame': makeColorMapBySystemVsApplicationFrame,
      },
      CPU_CHART_COLORS: chartColors.map(c => hexToColorChannels(c, 0.8)),
      MEMORY_CHART_COLORS: [
        hexToColorChannels(chartColors[2], 0.5),
        hexToColorChannels(chartColors[3], 0.5),
      ],
      CHART_CURSOR_INDICATOR: 'rgba(255, 255, 255, 0.5)',
      CHART_LABEL_COLOR: 'rgba(255, 255, 255, 0.5)',
      CURSOR_CROSSHAIR: '#828285',
      DIFFERENTIAL_DECREASE: [0.309, 0.2058, 0.98],
      DIFFERENTIAL_INCREASE: [0.98, 0.2058, 0.4381],
      FOCUSED_FRAME_BORDER_COLOR: theme.focus,
      FRAME_FALLBACK_COLOR: [0.5, 0.5, 0.5, 0.4],
      FRAME_APPLICATION_COLOR: [0.1, 0.1, 0.5, 0.4],
      FRAME_SYSTEM_COLOR: [0.6, 0.15, 0.25, 0.3],
      SPAN_FALLBACK_COLOR: [1, 1, 1, 0.3],
      GRID_FRAME_BACKGROUND_COLOR: 'rgb(26, 20, 31,1)',
      GRID_LINE_COLOR: '#222227',
      HIGHLIGHTED_LABEL_COLOR: 'rgba(136, 50, 0, 1)',
      HOVERED_FRAME_BORDER_COLOR: 'rgba(255, 255, 255, 0.8)',
      LABEL_FONT_COLOR: 'rgba(255, 255, 255, 0.8)',
      MINIMAP_POSITION_OVERLAY_BORDER_COLOR: 'rgba(255,255,255, 0.35)',
      MINIMAP_POSITION_OVERLAY_COLOR: 'rgba(82, 25, 25, 0.1)',
      SAMPLE_TICK_COLOR: [255, 0, 0, 0.5],
      // Yellow 200
      UI_FRAME_COLOR_SLOW: [0.96, 0.69, 0.0, 0.6],
      // Red 200 but stronger opacity
      UI_FRAME_COLOR_FROZEN: [0.96, 0.329, 0.349, 0.5],
      SEARCH_RESULT_FRAME_COLOR: 'vec4(0.99, 0.70, 0.35, 0.7)',
      SPAN_FRAME_LINE_PATTERN: '#594b66',
      SPAN_FRAME_LINE_PATTERN_BACKGROUND: '#1a1724',
      SELECTED_FRAME_BORDER_COLOR: theme.blue400,
      SEARCH_RESULT_SPAN_COLOR: '#b9834a',
      SPAN_FRAME_BORDER: '#57575b',
      STACK_TO_COLOR: makeStackToColor([1, 1, 1, 0.1]),
    },
  };
}

/** Chonk theme definitions */

const LCH_LIGHT_CHONK = {
  C_0: 0.35,
  C_d: 0.3,
  L_0: 0.8,
  L_d: 0.15,
};

const SPAN_LCH_LIGHT_CHONK = {
  C_0: 0.3,
  C_d: 0.25,
  L_0: 0.8,
  L_d: 0.15,
};

export const makeLightChonkFlamegraphTheme = (
  theme: DO_NOT_USE_ChonkTheme
): FlamegraphTheme => {
  const chartColors = theme.chart.getColorPalette(12);

  return {
    LCH: LCH_LIGHT_CHONK,
    SIZES: {
      ...SIZES,
      TIMELINE_LABEL_HEIGHT: 26,
    },
    FONTS: makeFlamegraphFonts(theme),
    COLORS: {
      COLOR_BUCKET: makeColorBucketTheme(LCH_LIGHT_CHONK),
      SPAN_COLOR_BUCKET: makeColorBucketTheme(SPAN_LCH_LIGHT_CHONK, 140, 220),
      COLOR_MAPS: {
        'by symbol name': makeColorMapBySymbolName,
        'by system frame': makeColorMapBySystemFrame,
        'by application frame': makeColorMapByApplicationFrame,
        'by library': makeColorMapByLibrary,
        'by recursion': makeColorMapByRecursion,
        'by frequency': makeColorMapByFrequency,
        'by system vs application frame': makeColorMapBySystemVsApplicationFrame,
      },

      // Charts
      CPU_CHART_COLORS: chartColors.map(c => hexToColorChannels(c, 0.8)),
      MEMORY_CHART_COLORS: [
        hexToColorChannels(theme.colors.yellow400, 1),
        hexToColorChannels(theme.colors.red400, 1),
      ],
      UI_FRAME_COLOR_SLOW: hexToColorChannels(theme.colors.yellow300, 1),
      UI_FRAME_COLOR_FROZEN: hexToColorChannels(theme.colors.red400, 1),
      BATTERY_CHART_COLORS: [hexToColorChannels(theme.colors.blue400, 1)],

      // Preset colors
      FRAME_APPLICATION_COLOR: hexToColorChannels(theme.colors.blue400, 0.4),
      FRAME_SYSTEM_COLOR: hexToColorChannels(theme.colors.red400, 0.3),
      DIFFERENTIAL_DECREASE: hexToColorChannels(theme.colors.blue400, 0.6),
      DIFFERENTIAL_INCREASE: hexToColorChannels(theme.colors.red400, 0.4),
      SAMPLE_TICK_COLOR: hexToColorChannels(theme.colors.red400, 0.5),

      // Cursors and labels
      LABEL_FONT_COLOR: theme.textColor,
      BAR_LABEL_FONT_COLOR: theme.textColor,
      CHART_CURSOR_INDICATOR: theme.subText,
      CHART_LABEL_COLOR: theme.subText,
      CURSOR_CROSSHAIR: theme.border,

      // Special states
      FOCUSED_FRAME_BORDER_COLOR: theme.focus,
      HIGHLIGHTED_LABEL_COLOR: `rgba(240, 240, 0, 1)`,
      HOVERED_FRAME_BORDER_COLOR: theme.colors.gray400,
      SELECTED_FRAME_BORDER_COLOR: theme.blue400,

      // Search results
      SEARCH_RESULT_FRAME_COLOR: 'vec4(0.99, 0.70, 0.35, 1.0)',
      SEARCH_RESULT_SPAN_COLOR: '#fdb359',

      // Patterns
      SPAN_FRAME_LINE_PATTERN_BACKGROUND: theme.colors.gray100,
      SPAN_FRAME_LINE_PATTERN: theme.colors.gray200,

      // Fallbacks
      SPAN_FALLBACK_COLOR: [0, 0, 0, 0.1],
      FRAME_FALLBACK_COLOR: [0.5, 0.5, 0.6, 0.1],

      // Layout colors
      GRID_LINE_COLOR: theme.colors.surface200,
      GRID_FRAME_BACKGROUND_COLOR: theme.colors.surface400,

      MINIMAP_POSITION_OVERLAY_BORDER_COLOR: theme.colors.gray300,
      MINIMAP_POSITION_OVERLAY_COLOR: theme.colors.gray200,

      SPAN_FRAME_BORDER: theme.colors.gray300,
      STACK_TO_COLOR: makeStackToColor([0, 0, 0, 0.035]),
    },
  };
};

const LCH_DARK_CHONK = {
  C_0: 0.35,
  C_d: 0.25,
  L_0: 0.25,
  L_d: 0.15,
};

const SPANS_LCH_DARK_CHONK = {
  C_0: 0.4,
  C_d: 0.25,
  L_0: 0.3,
  L_d: 0.2,
};

export const makeDarkChonkFlamegraphTheme = (
  theme: DO_NOT_USE_ChonkTheme
): FlamegraphTheme => {
  const chartColors = theme.chart.getColorPalette(12);
  return {
    LCH: LCH_DARK_CHONK,
    SIZES: {
      ...SIZES,
      TIMELINE_LABEL_HEIGHT: 26,
    },
    FONTS: makeFlamegraphFonts(theme),
    COLORS: {
      COLOR_BUCKET: makeColorBucketTheme(LCH_DARK_CHONK),
      SPAN_COLOR_BUCKET: makeColorBucketTheme(SPANS_LCH_DARK_CHONK, 140, 220),
      COLOR_MAPS: {
        'by symbol name': makeColorMapBySymbolName,
        'by system frame': makeColorMapBySystemFrame,
        'by application frame': makeColorMapByApplicationFrame,
        'by library': makeColorMapByLibrary,
        'by recursion': makeColorMapByRecursion,
        'by frequency': makeColorMapByFrequency,
        'by system vs application frame': makeColorMapBySystemVsApplicationFrame,
      },

      // Charts
      CPU_CHART_COLORS: chartColors.map(c => hexToColorChannels(c, 0.8)),
      MEMORY_CHART_COLORS: [
        hexToColorChannels(theme.colors.yellow400, 1),
        hexToColorChannels(theme.colors.red400, 1),
      ],
      UI_FRAME_COLOR_SLOW: hexToColorChannels(theme.colors.yellow300, 1),
      UI_FRAME_COLOR_FROZEN: hexToColorChannels(theme.colors.red400, 1),
      BATTERY_CHART_COLORS: [hexToColorChannels(theme.colors.blue400, 1)],

      // Preset colors
      FRAME_APPLICATION_COLOR: hexToColorChannels(theme.colors.blue400, 0.6),
      FRAME_SYSTEM_COLOR: hexToColorChannels(theme.colors.red400, 0.5),
      DIFFERENTIAL_DECREASE: hexToColorChannels(theme.colors.blue400, 0.6),
      DIFFERENTIAL_INCREASE: hexToColorChannels(theme.colors.red400, 0.4),
      SAMPLE_TICK_COLOR: hexToColorChannels(theme.colors.red400, 0.5),

      // Cursors and labels
      LABEL_FONT_COLOR: theme.textColor,
      BAR_LABEL_FONT_COLOR: theme.textColor,
      CHART_CURSOR_INDICATOR: theme.subText,
      CHART_LABEL_COLOR: theme.subText,
      CURSOR_CROSSHAIR: theme.border,

      // Special states
      FOCUSED_FRAME_BORDER_COLOR: theme.focus,
      HIGHLIGHTED_LABEL_COLOR: theme.colors.yellow400,
      HOVERED_FRAME_BORDER_COLOR: theme.colors.gray400,
      SELECTED_FRAME_BORDER_COLOR: theme.blue400,

      // Search results
      SEARCH_RESULT_FRAME_COLOR: 'vec4(0.99, 0.70, 0.35, 1.0)',
      SEARCH_RESULT_SPAN_COLOR: '#fdb359',

      // Patterns
      SPAN_FRAME_LINE_PATTERN: theme.colors.gray200,
      SPAN_FRAME_LINE_PATTERN_BACKGROUND: theme.colors.gray100,

      // Fallbacks
      FRAME_FALLBACK_COLOR: [0.5, 0.5, 0.5, 0.4],
      SPAN_FALLBACK_COLOR: [1, 1, 1, 0.3],

      // Layout colors
      GRID_LINE_COLOR: theme.colors.surface200,
      GRID_FRAME_BACKGROUND_COLOR: theme.colors.surface400,
      MINIMAP_POSITION_OVERLAY_BORDER_COLOR: theme.colors.gray300,
      MINIMAP_POSITION_OVERLAY_COLOR: theme.colors.gray200,

      SPAN_FRAME_BORDER: theme.colors.gray300,
      STACK_TO_COLOR: makeStackToColor([1, 1, 1, 0.18]),
    },
  };
};
