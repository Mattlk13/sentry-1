import {forwardRef} from 'react';
import {useTheme} from '@emotion/react';

import {IconUnsubscribed} from 'sentry/icons/iconUnsubscribed';

import type {SVGIconProps} from './svgIcon';
import {SvgIcon} from './svgIcon';

/**
 * @deprecated use IconUnsubscribed instead
 */
const IconMute = forwardRef<SVGSVGElement, SVGIconProps>((props, ref) => {
  const theme = useTheme();
  if (theme.isChonk) {
    return <IconUnsubscribed {...props} ref={ref} />;
  }

  return (
    <SvgIcon {...props} ref={ref} kind="path">
      <path d="M1.23,15.47a.75.75,0,0,1-.53-.22.74.74,0,0,1,0-1.06L14.24.64a.75.75,0,0,1,1.06,0,.74.74,0,0,1,0,1.06L1.76,15.25A.79.79,0,0,1,1.23,15.47Z" />
      <path d="M9.58,15.94a.71.71,0,0,1-.44-.15L3.58,11.73H.75A.75.75,0,0,1,0,11V5A.76.76,0,0,1,.75,4.2H3.58L9.14.14A.73.73,0,0,1,9.92.08a.75.75,0,0,1,.41.67V15.19a.73.73,0,0,1-.41.66A.69.69,0,0,1,9.58,15.94ZM1.5,10.23H3.83a.73.73,0,0,1,.44.15l4.56,3.33V2.22L4.27,5.56a.79.79,0,0,1-.44.14H1.5Z" />
      <path d="M13.92,11.79a.77.77,0,0,1-.53-.21.75.75,0,0,1,0-1.06,3.6,3.6,0,0,0,0-5.1.77.77,0,0,1,0-1.07.75.75,0,0,1,1.06,0,5.11,5.11,0,0,1,0,7.22A.75.75,0,0,1,13.92,11.79Z" />
      <path d="M11.76,10.35a.64.64,0,0,1-.33-.08.75.75,0,0,1-.34-1,.78.78,0,0,1,.14-.2,1.56,1.56,0,0,0,0-2.21A.75.75,0,0,1,12.29,5.8a3.07,3.07,0,0,1,0,4.32A.78.78,0,0,1,11.76,10.35Z" />
    </SvgIcon>
  );
});

IconMute.displayName = 'IconMute';

export {IconMute};
