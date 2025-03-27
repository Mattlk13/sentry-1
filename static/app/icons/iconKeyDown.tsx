import {Fragment} from 'react';
import {useTheme} from '@emotion/react';

import type {SVGIconProps} from './svgIcon';
import {SvgIcon} from './svgIcon';

function IconKeyDown({ref, ...props}: SVGIconProps) {
  const theme = useTheme();
  return (
    <SvgIcon {...props} ref={ref} kind={theme.isChonk ? 'stroke' : 'path'}>
      {theme.isChonk ? (
        <Fragment>
          <path d="m11.08,5.42l-2.41,2.21c-.38.35-.97.35-1.35,0l-2.49-2.29" />
          <line x1="8" y1="2" x2="8" y2="7.75" />
          <path d="m8,10.5c-1.56,0-2.66-.18-3.49-.4-.64-.17-1.26.31-1.26.96v2.18h9.5v-2.18c0-.66-.62-1.13-1.26-.96-.83.22-1.93.4-3.49.4Z" />
        </Fragment>
      ) : (
        <Fragment>
          <path d="M15.25,13.75H14v-2.5c0-0.57-0.27-1.11-0.71-1.44s-0.98-0.43-1.5-0.28l-0.15,0.04C10.77,9.83,9.3,10.25,8,10.25 c-1.3,0-2.77-0.42-3.65-0.68L4.21,9.53c-0.52-0.15-1.07-0.05-1.5,0.28C2.27,10.14,2,10.68,2,11.25v2.5H0.75 C0.33,13.75,0,14.09,0,14.5c0,0.41,0.33,0.75,0.75,0.75h14.5c0.41,0,0.75-0.34,0.75-0.75C16,14.09,15.66,13.75,15.25,13.75z M3.5,11.25c0-0.1,0.04-0.19,0.11-0.25c0.08-0.06,0.16-0.04,0.18-0.03l0.15,0.04c0.95,0.28,2.54,0.74,4.06,0.74 c1.52,0,3.11-0.46,4.06-0.74l0.15-0.04c0.02-0.01,0.1-0.03,0.17,0.03c0.08,0.06,0.12,0.15,0.12,0.25v2.5h-9V11.25z" />
          <path d="M11.51,5.8L8.53,8.53L8.51,8.55C8.4,8.64,8.28,8.71,8.15,8.73C8.1,8.74,8.05,8.75,8,8.75c-0.05,0-0.1-0.01-0.15-0.02 C7.72,8.71,7.6,8.64,7.49,8.55L7.47,8.53L4.49,5.8c-0.3-0.28-0.32-0.75-0.04-1.06C4.73,4.44,5.2,4.42,5.51,4.7l1.74,1.59V0.75 C7.25,0.34,7.59,0,8,0c0.41,0,0.75,0.34,0.75,0.75v5.54l1.74-1.59c0.31-0.28,0.78-0.26,1.06,0.04C11.83,5.05,11.81,5.52,11.51,5.8z" />
        </Fragment>
      )}
    </SvgIcon>
  );
}

IconKeyDown.displayName = 'IconKeyDown';

export {IconKeyDown};
