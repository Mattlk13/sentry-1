import type {ReactElement} from 'react';
import {useLayoutEffect, useMemo, useState} from 'react';
import * as Sentry from '@sentry/react';
import type {mat3} from 'gl-matrix';
import {vec2} from 'gl-matrix';

import {addErrorMessage} from 'sentry/actionCreators/indicator';
import {FlamegraphContextMenu} from 'sentry/components/profiling/flamegraph/flamegraphContextMenu';
import {FlamegraphZoomView} from 'sentry/components/profiling/flamegraph/flamegraphZoomView';
import type {
  CanvasPoolManager,
  CanvasScheduler,
} from 'sentry/utils/profiling/canvasScheduler';
import {CanvasView} from 'sentry/utils/profiling/canvasView';
import type {DifferentialFlamegraph as DifferentialFlamegraphModel} from 'sentry/utils/profiling/differentialFlamegraph';
import {useFlamegraphPreferences} from 'sentry/utils/profiling/flamegraph/hooks/useFlamegraphPreferences';
import {useFlamegraphTheme} from 'sentry/utils/profiling/flamegraph/useFlamegraphTheme';
import {FlamegraphCanvas} from 'sentry/utils/profiling/flamegraphCanvas';
import type {FlamegraphFrame} from 'sentry/utils/profiling/flamegraphFrame';
import {
  computeConfigViewWithStrategy,
  initializeFlamegraphRenderer,
  useResizeCanvasObserver,
} from 'sentry/utils/profiling/gl/utils';
import type {ProfileGroup} from 'sentry/utils/profiling/profile/importProfile';
import {FlamegraphRenderer2D} from 'sentry/utils/profiling/renderers/flamegraphRenderer2D';
import {FlamegraphRendererWebGL} from 'sentry/utils/profiling/renderers/flamegraphRendererWebGL';
import {Rect} from 'sentry/utils/profiling/speedscope';

interface DifferentialFlamegraphProps {
  canvasPoolManager: CanvasPoolManager;
  differentialFlamegraph: DifferentialFlamegraphModel;
  profileGroup: ProfileGroup;
  scheduler: CanvasScheduler;
}

export function DifferentialFlamegraph(props: DifferentialFlamegraphProps): ReactElement {
  const flamegraphTheme = useFlamegraphTheme();
  const {colorCoding} = useFlamegraphPreferences();

  const [flamegraphCanvasRef, setFlamegraphCanvasRef] =
    useState<HTMLCanvasElement | null>(null);
  const [flamegraphOverlayCanvasRef, setFlamegraphOverlayCanvasRef] =
    useState<HTMLCanvasElement | null>(null);

  const flamegraphCanvas = useMemo(() => {
    if (!flamegraphCanvasRef) {
      return null;
    }
    return new FlamegraphCanvas(flamegraphCanvasRef, vec2.fromValues(0, 0));
  }, [flamegraphCanvasRef]);

  const flamegraphView = useMemo<CanvasView<DifferentialFlamegraphModel> | null>(
    () => {
      if (!flamegraphCanvas || !props.differentialFlamegraph) {
        return null;
      }

      const newView = new CanvasView({
        canvas: flamegraphCanvas,
        model: props.differentialFlamegraph,
        options: {
          inverted: props.differentialFlamegraph.inverted,
          minWidth: props.differentialFlamegraph.profile.minFrameDuration,
          barHeight: flamegraphTheme.SIZES.BAR_HEIGHT,
          depthOffset: flamegraphTheme.SIZES.AGGREGATE_FLAMEGRAPH_DEPTH_OFFSET,
          configSpaceTransform: undefined,
        },
      });

      return newView;
    },

    // We skip position.view dependency because it will go into an infinite loop

    [props.differentialFlamegraph, flamegraphCanvas, flamegraphTheme]
  );

  // Uses a useLayoutEffect to ensure that these top level/global listeners are added before
  // any of the children components effects actually run. This way we do not lose events
  // when we register/unregister these top level listeners.
  useLayoutEffect(() => {
    if (!flamegraphCanvas || !flamegraphView) {
      return undefined;
    }

    // This code below manages the synchronization of the config views between spans and flamegraph
    // We do so by listening to the config view change event and then updating the other views accordingly which
    // allows us to keep the X axis in sync between the two views but keep the Y axis independent
    const onConfigViewChange = (rect: Rect, sourceConfigViewChange: CanvasView<any>) => {
      if (sourceConfigViewChange === flamegraphView) {
        flamegraphView.setConfigView(rect.withHeight(flamegraphView.configView.height));
      }

      props.canvasPoolManager.draw();
    };

    const onTransformConfigView = (
      mat: mat3,
      sourceTransformConfigView: CanvasView<any>
    ) => {
      if (sourceTransformConfigView === flamegraphView) {
        flamegraphView.transformConfigView(mat);
      }

      props.canvasPoolManager.draw();
    };

    const onResetZoom = () => {
      flamegraphView.resetConfigView(flamegraphCanvas);
      props.canvasPoolManager.draw();
    };

    const onZoomIntoFrame = (frame: FlamegraphFrame, strategy: 'min' | 'exact') => {
      const newConfigView = computeConfigViewWithStrategy(
        strategy,
        flamegraphView.configView,
        new Rect(frame.start, frame.depth, frame.end - frame.start, 1)
      ).transformRect(flamegraphView.configSpaceTransform);

      flamegraphView.setConfigView(newConfigView);

      props.canvasPoolManager.draw();
    };

    props.scheduler.on('set config view', onConfigViewChange);
    props.scheduler.on('transform config view', onTransformConfigView);
    props.scheduler.on('reset zoom', onResetZoom);
    props.scheduler.on('zoom at frame', onZoomIntoFrame);

    return () => {
      props.scheduler.off('set config view', onConfigViewChange);
      props.scheduler.off('transform config view', onTransformConfigView);
      props.scheduler.off('reset zoom', onResetZoom);
      props.scheduler.off('zoom at frame', onZoomIntoFrame);
    };
  }, [props.canvasPoolManager, flamegraphCanvas, flamegraphView, props.scheduler]);

  const flamegraphCanvases = useMemo(() => {
    return [flamegraphCanvasRef, flamegraphOverlayCanvasRef];
  }, [flamegraphCanvasRef, flamegraphOverlayCanvasRef]);

  useResizeCanvasObserver(
    flamegraphCanvases,
    props.canvasPoolManager,
    flamegraphCanvas,
    flamegraphView
  );

  const flamegraphRenderer = useMemo(() => {
    if (!flamegraphCanvasRef || !props.differentialFlamegraph) {
      return null;
    }

    const renderer = initializeFlamegraphRenderer(
      [FlamegraphRendererWebGL, FlamegraphRenderer2D],
      [
        flamegraphCanvasRef,
        props.differentialFlamegraph,
        flamegraphTheme,
        {
          colorCoding,
          draw_border: true,
        },
      ]
    );

    if (renderer === null) {
      Sentry.captureException('Failed to initialize a flamegraph renderer');
      addErrorMessage('Failed to initialize renderer');
      return null;
    }

    return renderer;
  }, [colorCoding, props.differentialFlamegraph, flamegraphCanvasRef, flamegraphTheme]);

  return (
    <FlamegraphZoomView
      scheduler={props.scheduler}
      profileGroup={props.profileGroup}
      disableGrid
      disableCallOrderSort
      disableColorCoding
      canvasPoolManager={props.canvasPoolManager}
      flamegraph={props.differentialFlamegraph}
      flamegraphRenderer={flamegraphRenderer}
      flamegraphCanvas={flamegraphCanvas}
      flamegraphCanvasRef={flamegraphCanvasRef}
      flamegraphOverlayCanvasRef={flamegraphOverlayCanvasRef}
      flamegraphView={flamegraphView}
      setFlamegraphCanvasRef={setFlamegraphCanvasRef}
      setFlamegraphOverlayCanvasRef={setFlamegraphOverlayCanvasRef}
      contextMenu={FlamegraphContextMenu}
    />
  );
}
