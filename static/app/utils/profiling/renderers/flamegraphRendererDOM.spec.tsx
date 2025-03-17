import {vec2} from 'gl-matrix';

import {makeCanvasMock, makeFlamegraph} from 'sentry-test/profiling/utils';
import {screen} from 'sentry-test/reactTestingLibrary';

import {makeLightFlamegraphTheme} from 'sentry/utils/profiling/flamegraph/flamegraphTheme';
import {FlamegraphRendererDOM} from 'sentry/utils/profiling/renderers/flamegraphRendererDOM';
import {lightTheme} from 'sentry/utils/theme';

import {CanvasView} from '../canvasView';
import type {Flamegraph} from '../flamegraph';
import {FlamegraphCanvas} from '../flamegraphCanvas';

const theme = makeLightFlamegraphTheme(lightTheme);
const originalDpr = window.devicePixelRatio;

describe('FlamegraphDomRenderer', () => {
  beforeEach(() => {
    // We simulate regular screens unless differently specified
    window.devicePixelRatio = 1;
  });
  afterEach(() => {
    window.devicePixelRatio = originalDpr;
  });

  it('renders a node', async () => {
    const flamegraph = makeFlamegraph(
      {
        endValue: 2,
        events: [
          {type: 'O', at: 0, frame: 0},
          {type: 'C', at: 2, frame: 0},
        ],
      },
      [{name: 'function 0'}]
    );

    const canvas = makeCanvasMock();

    // @ts-expect-error parentElement is a mock so readonly does not apply
    canvas.parentElement = document.createElement('div');
    document.body.appendChild(canvas.parentElement);

    const renderer = new FlamegraphRendererDOM(canvas, flamegraph, theme);
    const flamegraphCanvas = new FlamegraphCanvas(canvas, vec2.fromValues(0, 0));

    const flamegraphView = new CanvasView<Flamegraph>({
      canvas: flamegraphCanvas,
      model: flamegraph,
      options: {
        inverted: flamegraph.inverted,
        minWidth: flamegraph.profile.minFrameDuration,
        barHeight: theme.SIZES.BAR_HEIGHT,
        depthOffset: theme.SIZES.FLAMEGRAPH_DEPTH_OFFSET,
      },
    });

    renderer.draw(flamegraphView.fromConfigView(flamegraphCanvas.physicalSpace));

    expect(await screen.findByText(/function 0/)).toBeInTheDocument();
  });
});
