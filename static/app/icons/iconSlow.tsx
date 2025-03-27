import {Fragment} from 'react';
import {useTheme} from '@emotion/react';

import type {SVGIconProps} from './svgIcon';
import {SvgIcon} from './svgIcon';

function IconSlow({ref, ...props}: SVGIconProps) {
  const theme = useTheme();
  return (
    <SvgIcon {...props} ref={ref} kind={theme.isChonk ? 'stroke' : 'path'}>
      {theme.isChonk ? (
        <Fragment>
          <line x1="12.5" y1="2.75" x2="12" y2="4.75" />
          <line x1="10" y1="2.75" x2="10.5" y2="4.75" />
          <path d="m12.19,4.75h-2.27c-.52,0-.95.39-1,.91l-.33,3.68c-.05.52-.48.91-1,.91h-3.59c-.55,0-1,.45-1,1h0c0,1.1.9,2,2,2h4.9c2.1,0,3.55-2.1,2.8-4.07l-.15-.4c-.19-.5-.17-1.06.05-1.55l.49-1.07c.31-.66-.18-1.42-.91-1.42Z" />
          <path d="m8.75,5.45l-.84-.84c-1.12-1.12-2.94-1.12-4.07,0l-.25.25c-1.12,1.12-1.12,2.94,0,4.07l1.08,1.08" />
          <path d="m8.5,7.96c-1.11.55-2.5-.05-2.72-1.18v-.02" />
        </Fragment>
      ) : (
        <Fragment>
          <path d="m11.28,15.84H.76c-.41,0-.75-.34-.75-.75,0-.15.03-3.66,2.66-4.24.4-.09.81.17.89.57.09.4-.17.8-.57.89-.93.21-1.28,1.27-1.4,2.02h9.69c1.19,0,2.23-.35,2.77-.94.35-.38.5-.84.45-1.41-.14-1.76-.5-2.57-.63-2.87-.68-1.57-.57-2.09.07-2.89.17-.21.35-.44.55-.82.09-.47-.03-.87-.35-1.17-.42-.38-1.09-.52-1.68-.33-.46.14-1.05.53-1.27,1.57-.09.41-.49.66-.89.58-.41-.09-.66-.49-.58-.89.29-1.34,1.12-2.32,2.29-2.68,1.1-.35,2.34-.09,3.15.66.73.67,1.01,1.65.77,2.68-.01.05-.03.1-.05.15-.28.59-.57.95-.77,1.2-.27.33-.29.36.11,1.29.18.42.61,1.39.78,3.41.08.98-.21,1.86-.84,2.54-.83.9-2.24,1.42-3.87,1.42Z" />
          <path d="m6.31,13.67c-.98,0-1.94-.24-2.81-.7-1.62-.87-2.79-2.45-3.3-4.45C-.21,6.9.04,5.22.89,3.79c.85-1.43,2.21-2.45,3.83-2.86,2.73-.69,5.52.95,6.24,3.66.96,2.22,1.09,4.17.41,5.81-.88,2.1-2.8,2.86-2.88,2.89-.72.26-1.46.38-2.18.38Zm-.33-11.41c-.3,0-.6.04-.9.11-1.23.31-2.26,1.08-2.91,2.17-.65,1.09-.83,2.37-.52,3.6.41,1.59,1.31,2.83,2.56,3.5,1.13.61,2.47.69,3.76.23h0s1.4-.58,2.02-2.08c.2-.49.3-1.02.3-1.6-.58.81-1.43,1.38-2.41,1.63-1.91.49-3.85-.67-4.33-2.58-.41-1.6.56-3.24,2.17-3.65,1.36-.35,2.75.48,3.1,1.84.1.4-.14.81-.54.91-.4.1-.81-.14-.91-.54-.14-.56-.71-.9-1.28-.76-.8.2-1.29,1.02-1.08,1.83.28,1.1,1.4,1.77,2.51,1.49.72-.18,1.32-.63,1.7-1.27.38-.63.48-1.37.31-2.09,0,0,0-.01,0-.02-.42-1.64-1.91-2.74-3.53-2.74Z" />
          <path d="m11.51,4.32c-.28,0-.55-.16-.68-.43-.1-.21-.94-2.08.08-3.43.25-.33.72-.4,1.05-.15.33.25.4.72.15,1.05-.42.56-.04,1.63.08,1.89.18.37.02.82-.36,1-.1.05-.21.07-.32.07Z" />
          <path d="m14.04,4.05s-.07,0-.1,0c-.41-.05-.7-.43-.65-.84.03-.2.29-1.98,1.44-2.88.33-.26.8-.2,1.05.13.26.33.2.8-.13,1.05-.57.45-.83,1.52-.88,1.9-.05.38-.37.65-.74.65Z" />
        </Fragment>
      )}
    </SvgIcon>
  );
}

IconSlow.displayName = 'IconSlow';

export {IconSlow};
