import {forwardRef, Fragment} from 'react';
import {useTheme} from '@emotion/react';

import type {SVGIconProps} from './svgIcon';
import {SvgIcon} from './svgIcon';

const IconStats = forwardRef<SVGSVGElement, SVGIconProps>((props, ref) => {
  const theme = useTheme();
  return (
    <SvgIcon {...props} ref={ref} kind={theme.isChonk ? 'stroke' : 'path'}>
      {theme.isChonk ? (
        <Fragment>
          <line x1="5.5" y1="13.25" x2="5.5" y2="10.75" />
          <line x1="3" y1="13.25" x2="3" y2="11.25" />
          <line x1="8" y1="13.25" x2="8" y2="9" />
          <line x1="10.5" y1="13.25" x2="10.5" y2="8.5" />
          <line x1="13" y1="13.25" x2="13" y2="6.5" />
          <polyline points="3 8 5.5 7.5 8 3.75 10.5 5 13 2.75" />
          <line x1="5.5" y1="13.25" x2="5.5" y2="10.75" />
          <line x1="3" y1="13.25" x2="3" y2="11.25" />
          <line x1="8" y1="13.25" x2="8" y2="9" />
          <line x1="10.5" y1="13.25" x2="10.5" y2="8.5" />
          <line x1="13" y1="13.25" x2="13" y2="6.5" />
          <line x1="5.5" y1="13.25" x2="5.5" y2="10.75" />
          <line x1="3" y1="13.25" x2="3" y2="11.25" />
          <line x1="8" y1="13.25" x2="8" y2="9" />
          <line x1="10.5" y1="13.25" x2="10.5" y2="8.5" />
          <line x1="13" y1="13.25" x2="13" y2="6.5" />
          <line x1="5.5" y1="13.25" x2="5.5" y2="10.75" />
          <line x1="3" y1="13.25" x2="3" y2="11.25" />
          <line x1="8" y1="13.25" x2="8" y2="9" />
          <line x1="10.5" y1="13.25" x2="10.5" y2="8.5" />
          <line x1="13" y1="13.25" x2="13" y2="6.5" />
        </Fragment>
      ) : (
        <Fragment>
          <path d="M13.25,16H2.75A2.75,2.75,0,0,1,0,13.25V2.75A2.75,2.75,0,0,1,2.75,0h10.5A2.75,2.75,0,0,1,16,2.75v10.5A2.75,2.75,0,0,1,13.25,16ZM2.75,1.5A1.25,1.25,0,0,0,1.5,2.75v10.5A1.25,1.25,0,0,0,2.75,14.5h10.5a1.25,1.25,0,0,0,1.25-1.25V2.75A1.25,1.25,0,0,0,13.25,1.5Z" />
          <path d="M3.59,15.65a.76.76,0,0,1-.75-.75V9.25a.75.75,0,0,1,1.5,0V14.9A.75.75,0,0,1,3.59,15.65Z" />
          <path d="M6.53,15.65a.76.76,0,0,1-.75-.75V9.25a.75.75,0,0,1,1.5,0V14.9A.76.76,0,0,1,6.53,15.65Z" />
          <path d="M9.47,15.65a.76.76,0,0,1-.75-.75V7.8a.75.75,0,1,1,1.5,0v7.1A.76.76,0,0,1,9.47,15.65Z" />
          <path d="M12.41,15.65a.75.75,0,0,1-.75-.75v-10a.75.75,0,1,1,1.5,0V14.9A.76.76,0,0,1,12.41,15.65Z" />
        </Fragment>
      )}
    </SvgIcon>
  );
});

IconStats.displayName = 'IconStats';

export {IconStats};
