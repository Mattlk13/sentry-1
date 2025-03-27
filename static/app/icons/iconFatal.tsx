import {forwardRef, Fragment} from 'react';
import {useTheme} from '@emotion/react';

import type {SVGIconProps} from './svgIcon';
import {SvgIcon} from './svgIcon';

const IconFatal = forwardRef<SVGSVGElement, SVGIconProps>((props, ref) => {
  const theme = useTheme();
  return (
    <SvgIcon {...props} ref={ref} kind={theme.isChonk ? 'stroke' : 'path'}>
      {theme.isChonk ? (
        <Fragment>
          <line x1="9.25" y1="13.25" x2="9.25" y2="11" />
          <line x1="6.75" y1="13" x2="6.75" y2="11.5" />
          <path d="m10.25,2.75h-4.5c-1.66,0-3,1.34-3,3v3.75c0,.83.67,1.5,1.5,1.5h0v1.25c0,.55.45,1,1,1h5.5c.55,0,1-.45,1-1v-1.25h0c.83,0,1.5-.67,1.5-1.5v-3.75c0-1.66-1.34-3-3-3Z" />
          <circle cx="10" cy="7.5" r=".5" />
          <circle cx="6" cy="7.5" r=".75" />
        </Fragment>
      ) : (
        <Fragment>
          <path d="M5.38,10.29A1.73,1.73,0,1,1,7.11,8.57,1.72,1.72,0,0,1,5.38,10.29Zm0-1.95a.22.22,0,0,0-.22.23c0,.25.45.25.45,0A.23.23,0,0,0,5.38,8.34Z" />
          <path d="M10.62,10.78a2.22,2.22,0,1,1,2.21-2.21A2.21,2.21,0,0,1,10.62,10.78Zm0-2.93a.72.72,0,1,0,.71.72A.72.72,0,0,0,10.62,7.85Z" />
          <path d="M11.71,16H4.29a.75.75,0,0,1-.75-.75V13.2A2.74,2.74,0,0,1,.59,10.55a2.47,2.47,0,0,1,.3-1.19,7,7,0,0,1-.69-3C.2,2.54,3.33,0,8,0s7.8,2.54,7.8,6.32a7,7,0,0,1-.69,3,2.47,2.47,0,0,1,.3,1.19,2.75,2.75,0,0,1-2.95,2.65v2.06A.75.75,0,0,1,11.71,16Zm-5.56-1.5V11.63a.75.75,0,0,1,1.5,0v2.88h.7V13.06a.75.75,0,0,1,1.5,0v1.45H11V12.24a.76.76,0,0,1,.36-.64.74.74,0,0,1,.72,0,1.38,1.38,0,0,0,.6.13,1.21,1.21,0,0,0,1.27-1.15,1.07,1.07,0,0,0-.22-.63.77.77,0,0,1-.1-.88,5.55,5.55,0,0,0,.71-2.72C14.3,2.76,10.91,1.5,8,1.5S1.7,2.76,1.7,6.32A5.55,5.55,0,0,0,2.41,9a.76.76,0,0,1-.11.88,1.13,1.13,0,0,0-.21.63A1.21,1.21,0,0,0,3.36,11.7a1.46,1.46,0,0,0,.55-.11.5.5,0,0,1,.2-.08A.75.75,0,0,1,5,11.9a.9.9,0,0,1,.08.36v2.25Z" />
        </Fragment>
      )}
    </SvgIcon>
  );
});

IconFatal.displayName = 'IconFatal';

export {IconFatal};
