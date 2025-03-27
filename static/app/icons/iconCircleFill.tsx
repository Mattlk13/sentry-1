import {forwardRef} from 'react';

import type {SVGIconProps} from './svgIcon';
import {SvgIcon} from './svgIcon';

/**
 * @deprecated This icon will be removed in new UI.
 */
const IconCircleFill = forwardRef<SVGSVGElement, SVGIconProps>((props, ref) => {
  return (
    <SvgIcon {...props} ref={ref} viewBox="0 0 24 24" kind="path">
      <circle cx="12" cy="12" r="10" />
    </SvgIcon>
  );
});

IconCircleFill.displayName = 'IconCircleFill';

export {IconCircleFill};
