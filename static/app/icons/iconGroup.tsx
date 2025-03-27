import {forwardRef, Fragment} from 'react';
import {useTheme} from '@emotion/react';

import type {SVGIconProps} from './svgIcon';
import {SvgIcon} from './svgIcon';

const IconGroup = forwardRef<SVGSVGElement, SVGIconProps>((props, ref) => {
  const theme = useTheme();
  return (
    <SvgIcon {...props} ref={ref} kind={theme.isChonk ? 'stroke' : 'path'}>
      {theme.isChonk ? (
        <Fragment>
          <rect x="4.75" y="3.25" width="3.5" height="5" rx="1.75" ry="1.75" />
          <path d="m4.75,8.25h3.5c1.1,0,2,.9,2,2v3H2.75v-3c0-1.1.9-2,2-2Z" />
          <path d="m9.5,2.25c.97,0,1.75.78,1.75,1.75v1.5c0,.48-.19.91-.5,1.22l.5.53c1.1,0,2,.9,2,2v3h-.75" />
        </Fragment>
      ) : (
        <Fragment>
          <path d="M6.53,11.76a3.31,3.31,0,0,1-3.31-3.3V6.28a3.31,3.31,0,1,1,6.62,0V8.46A3.31,3.31,0,0,1,6.53,11.76Zm0-7.29A1.81,1.81,0,0,0,4.72,6.28V8.46a1.81,1.81,0,0,0,3.62,0V6.28A1.81,1.81,0,0,0,6.53,4.47Z" />
          <path d="M11.49,16.05H1.57A1.54,1.54,0,0,1,0,14.5V13A3.12,3.12,0,0,1,2.65,9.88l2-.33A.75.75,0,0,1,4.87,11l-2,.33A1.62,1.62,0,0,0,1.53,13V14.5l10,.05,0-1.58a1.62,1.62,0,0,0-1.36-1.61l-2-.33a.75.75,0,0,1,.24-1.48l2,.33A3.12,3.12,0,0,1,13,13V14.5A1.54,1.54,0,0,1,11.49,16.05Z" />
          <path d="M9.47,8.87a4,4,0,0,1-.49,0A.75.75,0,0,1,8.35,8a.73.73,0,0,1,.85-.63l.27,0a1.81,1.81,0,0,0,1.81-1.81V3.38a1.81,1.81,0,0,0-3.62,0v.37a.75.75,0,0,1-1.5,0V3.38a3.31,3.31,0,0,1,6.62,0V5.56A3.32,3.32,0,0,1,9.47,8.87Z" />
          <path d="M14.43,13.15H12.21a.75.75,0,0,1,0-1.5h2.22l0-1.57A1.63,1.63,0,0,0,13.1,8.46l-2-.33a.75.75,0,0,1-.62-.86.76.76,0,0,1,.86-.62l2,.33A3.12,3.12,0,0,1,16,10.08v1.53A1.54,1.54,0,0,1,14.43,13.15Z" />
        </Fragment>
      )}
    </SvgIcon>
  );
});

IconGroup.displayName = 'IconGroup';

export {IconGroup};
