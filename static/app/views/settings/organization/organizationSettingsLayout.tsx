import {Fragment} from 'react';

import type {RouteComponentProps} from 'sentry/types/legacyReactRouter';
import {usePrefersStackedNav} from 'sentry/views/nav/prefersStackedNav';
import SettingsLayout from 'sentry/views/settings/components/settingsLayout';
import OrganizationSettingsNavigation from 'sentry/views/settings/organization/organizationSettingsNavigation';

type Props = RouteComponentProps & {
  children: React.ReactNode;
};

function OrganizationSettingsLayout(props: Props) {
  const prefersStackedNav = usePrefersStackedNav();

  if (prefersStackedNav) {
    return (
      <Fragment>
        <OrganizationSettingsNavigation />
        <SettingsLayout {...props} />
      </Fragment>
    );
  }

  return (
    <SettingsLayout
      {...props}
      renderNavigation={() => <OrganizationSettingsNavigation />}
    />
  );
}

export default OrganizationSettingsLayout;
