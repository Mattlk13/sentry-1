import type {MouseEventHandler} from 'react';
import {css, type Theme} from '@emotion/react';
import styled from '@emotion/styled';

import {DropdownMenu, type MenuItemProps} from 'sentry/components/dropdownMenu';
import InteractionStateLayer from 'sentry/components/interactionStateLayer';
import Link from 'sentry/components/links/link';
import {linkStyles} from 'sentry/components/links/styles';
import {useNavContext} from 'sentry/components/nav/context';
import {NavLayout} from 'sentry/components/nav/types';
import {isLinkActive, makeLinkPropsFromTo} from 'sentry/components/nav/utils';
import {Tooltip} from 'sentry/components/tooltip';
import {IconDefaultsProvider} from 'sentry/icons/useIconDefaults';
import {space} from 'sentry/styles/space';
import type {Organization} from 'sentry/types/organization';
import {trackAnalytics} from 'sentry/utils/analytics';
import normalizeUrl from 'sentry/utils/url/normalizeUrl';
import {useLocation} from 'sentry/utils/useLocation';
import useOrganization from 'sentry/utils/useOrganization';

interface SidebarItemLinkProps {
  analyticsKey: string;
  label: string;
  to: string;
  activeTo?: string;
  children?: React.ReactNode;
  forceLabel?: boolean;
  onClick?: MouseEventHandler<HTMLElement>;
}

interface SidebarItemDropdownProps {
  analyticsKey: string;
  items: MenuItemProps[];
  label: string;
  children?: React.ReactNode;
  forceLabel?: boolean;
}

interface SidebarButtonProps {
  analyticsKey: string;
  children: React.ReactNode;
  label: string;
  buttonProps?: React.HTMLAttributes<HTMLElement>;
  onClick?: MouseEventHandler<HTMLElement>;
}

function recordPrimaryItemClick(analyticsKey: string, organization: Organization) {
  trackAnalytics('navigation.primary_item_clicked', {
    item: analyticsKey,
    organization,
  });
}

export function SidebarItem({
  children,
  label,
  showLabel,
  ...props
}: {
  children: React.ReactNode;
  label: string;
  showLabel: boolean;
} & React.HTMLAttributes<HTMLElement>) {
  const {layout} = useNavContext();
  return (
    <IconDefaultsProvider legacySize={layout === NavLayout.MOBILE ? '14px' : '16px'}>
      <Tooltip title={label} disabled={showLabel} position="right" skipWrapper delay={0}>
        <li {...props}>{children}</li>
      </Tooltip>
    </IconDefaultsProvider>
  );
}

export function SidebarMenu({
  items,
  children,
  analyticsKey,
  label,
  forceLabel,
}: SidebarItemDropdownProps) {
  const organization = useOrganization();
  const {layout} = useNavContext();

  const showLabel = forceLabel || layout === NavLayout.MOBILE;

  return (
    <DropdownMenu
      position={layout === NavLayout.MOBILE ? 'bottom' : 'right-end'}
      shouldApplyMinWidth={false}
      trigger={(props, isOpen) => {
        return (
          <SidebarItem label={label} showLabel={showLabel}>
            <NavButton
              {...props}
              aria-label={showLabel ? undefined : label}
              onClick={event => {
                recordPrimaryItemClick(analyticsKey, organization);
                props.onClick?.(event);
              }}
              isMobile={layout === NavLayout.MOBILE}
            >
              <InteractionStateLayer hasSelectedBackground={isOpen} />
              {children}
              {showLabel ? label : null}
            </NavButton>
          </SidebarItem>
        );
      }}
      items={items}
    />
  );
}

export function SidebarLink({
  children,
  to,
  activeTo = to,
  analyticsKey,
  label,
  forceLabel = false,
}: SidebarItemLinkProps) {
  const organization = useOrganization();
  const location = useLocation();
  const isActive = isLinkActive(normalizeUrl(activeTo, location), location.pathname);
  const linkProps = makeLinkPropsFromTo(to);

  const {layout} = useNavContext();
  const showLabel = forceLabel || layout === NavLayout.MOBILE;

  return (
    <SidebarItem label={label} showLabel={showLabel}>
      <NavLink
        {...linkProps}
        onClick={() => recordPrimaryItemClick(analyticsKey, organization)}
        aria-selected={isActive}
        aria-current={isActive ? 'page' : undefined}
        aria-label={showLabel ? undefined : label}
        isMobile={layout === NavLayout.MOBILE}
      >
        <InteractionStateLayer hasSelectedBackground={isActive} />
        {children}
        {showLabel ? label : null}
      </NavLink>
    </SidebarItem>
  );
}

export function SidebarButton({
  analyticsKey,
  children,
  buttonProps = {},
  onClick,
  label,
}: SidebarButtonProps) {
  const organization = useOrganization();
  const {layout} = useNavContext();
  const showLabel = layout === NavLayout.MOBILE;

  return (
    <SidebarItem label={label} showLabel={showLabel}>
      <NavButton
        {...buttonProps}
        isMobile={layout === NavLayout.MOBILE}
        aria-label={showLabel ? undefined : label}
        onClick={(e: React.MouseEvent<HTMLElement>) => {
          recordPrimaryItemClick(analyticsKey, organization);
          buttonProps.onClick?.(e);
          onClick?.(e);
        }}
      >
        <InteractionStateLayer />
        {children}
        {showLabel ? label : null}
      </NavButton>
    </SidebarItem>
  );
}

export function SeparatorItem() {
  return (
    <SeparatorListItem aria-hidden>
      <Separator />
    </SeparatorListItem>
  );
}

const baseNavItemStyles = (p: {isMobile: boolean; theme: Theme}) => css`
  display: flex;
  flex-direction: row;
  gap: ${space(1.5)};
  align-items: center;
  padding: ${space(1.5)} ${space(3)};
  color: ${p.theme.textColor};
  font-size: ${p.theme.fontSizeMedium};
  font-weight: ${p.theme.fontWeightNormal};
  line-height: 1;
  width: 100%;

  &:hover {
    color: ${p.theme.textColor};
  }

  & > * {
    pointer-events: none;
  }

  &[aria-selected='true'] {
    color: ${p.theme.purple400};
    box-shadow: inset 0 0 0 1px ${p.theme.purple100};
  }

  ${!p.isMobile &&
  css`
    flex-direction: column;
    justify-content: center;
    border-radius: ${p.theme.borderRadius};
    margin-inline: 0 auto;
    gap: ${space(0.75)};
    padding: ${space(1.5)} 0;
    min-height: 40px;
    width: 44px;
    letter-spacing: -0.02em;
    font-size: 10px;
  `}
`;

export const NavLink = styled(Link, {
  shouldForwardProp: prop => prop !== 'isMobile',
})<{isMobile: boolean}>`
  position: relative;

  ${baseNavItemStyles}
`;

export const NavButton = styled('button', {
  shouldForwardProp: prop => prop !== 'isMobile',
})<{isMobile: boolean}>`
  border: none;
  position: relative;
  background: transparent;

  ${linkStyles}
  ${baseNavItemStyles}
`;

export const SidebarItemUnreadIndicator = styled('span')`
  position: absolute;
  top: calc(50% - 12px);
  left: calc(50% + 12px);
  transform: translate(-50%, -50%);
  display: block;
  text-align: center;
  color: ${p => p.theme.white};
  font-size: ${p => p.theme.fontSizeExtraSmall};
  background: ${p => p.theme.purple400};
  width: 10px;
  height: 10px;
  border-radius: 50%;
  border: 2px solid ${p => p.theme.background};
`;

const SeparatorListItem = styled('li')`
  list-style: none;
  width: 100%;
  padding: 0 ${space(1.5)};
`;

const Separator = styled('hr')`
  outline: 0;
  border: 0;
  height: 1px;
  background: ${p => p.theme.innerBorder};
  margin: 0;
`;
