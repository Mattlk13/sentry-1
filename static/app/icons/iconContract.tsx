import {Fragment} from 'react';
import {useTheme} from '@emotion/react';

import type {SVGIconProps} from './svgIcon';
import {SvgIcon} from './svgIcon';

function IconContract({ref, ...props}: SVGIconProps) {
  const theme = useTheme();
  return (
    <SvgIcon {...props} ref={ref} kind={theme.isChonk ? 'stroke' : 'path'}>
      {theme.isChonk ? (
        <Fragment>
          <path d="m5.75,2.75v2c0,.55-.45,1-1,1h-2" />
          <path d="m13.25,5.75h-2c-.55,0-1-.45-1-1v-2" />
          <path d="m10.25,13.25v-2c0-.55.45-1,1-1h2" />
          <path d="m2.75,10.25h2c.55,0,1,.45,1,1v2" />
        </Fragment>
      ) : (
        <Fragment>
          <path d="M5.02,16c-.41,0-.75-.34-.75-.75v-3.49H.78c-.41,0-.75-.34-.75-.75s.34-.75,.75-.75H5.02c.41,0,.75,.34,.75,.75v4.24c0,.41-.34,.75-.75,.75Z" />
          <path d="M11.05,16c-.41,0-.75-.34-.75-.75v-4.24c0-.41,.34-.75,.75-.75h4.22c.41,0,.75,.34,.75,.75s-.34,.75-.75,.75h-3.47v3.49c0,.41-.34,.75-.75,.75Z" />
          <path d="M5.01,5.73H.79c-.41,0-.75-.34-.75-.75s.34-.75,.75-.75h3.47V.76C4.26,.35,4.6,0,5.01,0s.75,.34,.75,.75V4.98c0,.41-.34,.75-.75,.75Z" />
          <path d="M15.27,5.73h-4.22c-.41,0-.75-.34-.75-.75V.76c0-.41,.34-.75,.75-.75s.75,.34,.75,.75v3.47h3.47c.41,0,.75,.34,.75,.75s-.34,.75-.75,.75Z" />
        </Fragment>
      )}
    </SvgIcon>
  );
}

IconContract.displayName = 'IconContract';

export {IconContract};
