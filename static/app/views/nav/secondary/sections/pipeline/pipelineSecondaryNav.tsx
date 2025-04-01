import {t} from 'sentry/locale';
import useOrganization from 'sentry/utils/useOrganization';
import {NAV_GROUP_LABELS} from 'sentry/views/nav/constants';
import {SecondaryNav} from 'sentry/views/nav/secondary/secondary';
import {PrimaryNavGroup} from 'sentry/views/nav/types';
import {makePipelinePathname} from 'sentry/views/pipeline/pathnames';
import {COVERAGE_BASE_URL, TESTS_BASE_URL} from 'sentry/views/pipeline/settings';

function PipelineSecondaryNav() {
  const organization = useOrganization();
  const coveragePathname = makePipelinePathname({
    organization,
    path: `/${COVERAGE_BASE_URL}/`,
  });
  const testsPathname = makePipelinePathname({
    organization,
    path: `/${TESTS_BASE_URL}/`,
  });

  return (
    <SecondaryNav>
      <SecondaryNav.Header>
        {NAV_GROUP_LABELS[PrimaryNavGroup.PIPELINE]}
      </SecondaryNav.Header>
      <SecondaryNav.Body>
        <SecondaryNav.Section>
          <SecondaryNav.Item to={coveragePathname}>{t('Coverage')}</SecondaryNav.Item>
          <SecondaryNav.Item to={testsPathname}>{t('Tests')}</SecondaryNav.Item>
        </SecondaryNav.Section>
      </SecondaryNav.Body>
    </SecondaryNav>
  );
}

export default PipelineSecondaryNav;
