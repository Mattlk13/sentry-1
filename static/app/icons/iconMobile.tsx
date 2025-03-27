import {Fragment} from 'react';
import {useTheme} from '@emotion/react';

import type {SVGIconProps} from './svgIcon';
import {SvgIcon} from './svgIcon';

function IconMobile({ref, ...props}: SVGIconProps) {
  const theme = useTheme();
  return (
    <SvgIcon {...props} ref={ref} kind={theme.isChonk ? 'stroke' : 'path'}>
      {theme.isChonk ? (
        <Fragment>
          <rect x="4.75" y="2.75" width="6.5" height="10.5" rx="1" ry="1" />
          <rect x="7.25" y="2.75" width="1.5" height=".75" />
        </Fragment>
      ) : (
        <Fragment>
          <path d="M11.63 16H4.37C3.90668 15.9974 3.46308 15.8122 3.13546 15.4845C2.80784 15.1569 2.62262 14.7133 2.62 14.25V1.75C2.62262 1.28668 2.80784 0.843085 3.13546 0.515464C3.46308 0.187842 3.90668 0.0026251 4.37 0L11.63 0C12.0933 0.0026251 12.5369 0.187842 12.8645 0.515464C13.1922 0.843085 13.3774 1.28668 13.38 1.75V14.25C13.3774 14.7133 13.1922 15.1569 12.8645 15.4845C12.5369 15.8122 12.0933 15.9974 11.63 16ZM4.37 1.5C4.30369 1.5 4.2401 1.52634 4.19322 1.57322C4.14633 1.62011 4.12 1.6837 4.12 1.75V14.25C4.12 14.3163 4.14633 14.3799 4.19322 14.4268C4.2401 14.4737 4.30369 14.5 4.37 14.5H11.63C11.6963 14.5 11.7599 14.4737 11.8068 14.4268C11.8537 14.3799 11.88 14.3163 11.88 14.25V1.75C11.88 1.6837 11.8537 1.62011 11.8068 1.57322C11.7599 1.52634 11.6963 1.5 11.63 1.5H4.37Z" />
          <path d="M10 2.66H6.19C5.99109 2.66 5.80032 2.58098 5.65967 2.44033C5.51902 2.29968 5.44 2.10891 5.44 1.91V0.75C5.44 0.551088 5.51902 0.360322 5.65967 0.21967C5.80032 0.0790176 5.99109 0 6.19 0C6.38891 0 6.57968 0.0790176 6.72033 0.21967C6.86098 0.360322 6.94 0.551088 6.94 0.75V1.16H9.23V0.75C9.23 0.551088 9.30902 0.360322 9.44967 0.21967C9.59032 0.0790176 9.78109 0 9.98 0C10.1789 0 10.3697 0.0790176 10.5103 0.21967C10.651 0.360322 10.73 0.551088 10.73 0.75V1.91C10.7276 2.10474 10.6505 2.29112 10.5147 2.43068C10.3788 2.57024 10.1946 2.65233 10 2.66Z" />
        </Fragment>
      )}
    </SvgIcon>
  );
}

IconMobile.displayName = 'IconMobile';

export {IconMobile};
