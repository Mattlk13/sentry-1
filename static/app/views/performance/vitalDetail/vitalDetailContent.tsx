import {Fragment, useState} from 'react';
import {useTheme} from '@emotion/react';
import styled from '@emotion/styled';
import type {Location} from 'history';
import omit from 'lodash/omit';

import type {Client} from 'sentry/api';
import Feature from 'sentry/components/acl/feature';
import {getInterval} from 'sentry/components/charts/utils';
import {Alert} from 'sentry/components/core/alert';
import {ButtonBar} from 'sentry/components/core/button/buttonBar';
import {CreateAlertFromViewButton} from 'sentry/components/createAlertButton';
import type {MenuItemProps} from 'sentry/components/dropdownMenu';
import {DropdownMenu} from 'sentry/components/dropdownMenu';
import * as Layout from 'sentry/components/layouts/thirds';
import LoadingIndicator from 'sentry/components/loadingIndicator';
import {DatePageFilter} from 'sentry/components/organizations/datePageFilter';
import {EnvironmentPageFilter} from 'sentry/components/organizations/environmentPageFilter';
import PageFilterBar from 'sentry/components/organizations/pageFilterBar';
import {normalizeDateTimeParams} from 'sentry/components/organizations/pageFilters/parse';
import {ProjectPageFilter} from 'sentry/components/organizations/projectPageFilter';
import * as TeamKeyTransactionManager from 'sentry/components/performance/teamKeyTransactionsManager';
import {TransactionSearchQueryBuilder} from 'sentry/components/performance/transactionSearchQueryBuilder';
import {IconCheckmark, IconClose} from 'sentry/icons';
import {t} from 'sentry/locale';
import {space} from 'sentry/styles/space';
import type {InjectedRouter} from 'sentry/types/legacyReactRouter';
import type {Organization} from 'sentry/types/organization';
import type {Project} from 'sentry/types/project';
import {trackAnalytics} from 'sentry/utils/analytics';
import {browserHistory} from 'sentry/utils/browserHistory';
import {getUtcToLocalDateObject} from 'sentry/utils/dates';
import type EventView from 'sentry/utils/discover/eventView';
import {WebVital} from 'sentry/utils/fields';
import {Browser} from 'sentry/utils/performance/vitals/constants';
import {decodeScalar} from 'sentry/utils/queryString';
import Teams from 'sentry/utils/teams';
import {MutableSearch} from 'sentry/utils/tokenizeSearch';
import withProjects from 'sentry/utils/withProjects';
import {deprecateTransactionAlerts} from 'sentry/views/insights/common/utils/hasEAPAlerts';
import Breadcrumb from 'sentry/views/performance/breadcrumb';
import {getTransactionSearchQuery} from 'sentry/views/performance/utils';

import Table from './table';
import {
  vitalAbbreviations,
  vitalAlertTypes,
  vitalDescription,
  vitalMap,
  vitalSupportedBrowsers,
} from './utils';
import VitalChart from './vitalChart';
import VitalInfo from './vitalInfo';

const FRONTEND_VITALS = [WebVital.FCP, WebVital.LCP, WebVital.FID, WebVital.CLS];

type Props = {
  api: Client;
  eventView: EventView;
  location: Location;
  organization: Organization;
  projects: Project[];
  router: InjectedRouter;
  vitalName: WebVital;
};

function getSummaryConditions(query: string) {
  const parsed = new MutableSearch(query);
  parsed.freeText = [];

  return parsed.formatString();
}

function VitalDetailContent(props: Props) {
  const theme = useTheme();
  const [error, setError] = useState<string | undefined>(undefined);
  function handleSearch(query: string) {
    const {location} = props;

    const queryParams = normalizeDateTimeParams({
      ...location.query,
      query,
    });

    // do not propagate pagination when making a new search
    const searchQueryParams = omit(queryParams, 'cursor');

    browserHistory.push({
      pathname: location.pathname,
      query: searchQueryParams,
    });
  }

  function renderCreateAlertButton() {
    const {eventView, organization, projects, vitalName} = props;

    return (
      <CreateAlertFromViewButton
        eventView={eventView}
        organization={organization}
        projects={projects}
        aria-label={t('Create Alert')}
        alertType={vitalAlertTypes[vitalName]}
        referrer="performance"
      />
    );
  }

  function renderVitalSwitcher() {
    const {vitalName, location, organization} = props;

    const position = FRONTEND_VITALS.indexOf(vitalName);

    if (position < 0) {
      return null;
    }

    const items: MenuItemProps[] = FRONTEND_VITALS.reduce(
      (acc: MenuItemProps[], newVitalName) => {
        const itemProps = {
          key: newVitalName,
          label: vitalAbbreviations[newVitalName],
          onAction: function switchWebVital() {
            browserHistory.push({
              pathname: location.pathname,
              query: {
                ...location.query,
                vitalName: newVitalName,
                cursor: undefined,
              },
            });

            trackAnalytics('performance_views.vital_detail.switch_vital', {
              organization,
              from_vital: vitalAbbreviations[vitalName] ?? 'undefined',
              to_vital: vitalAbbreviations[newVitalName] ?? 'undefined',
            });
          },
        };

        if (vitalName === newVitalName) {
          acc.unshift(itemProps);
        } else {
          acc.push(itemProps);
        }

        return acc;
      },
      []
    );

    return (
      <DropdownMenu
        items={items}
        triggerLabel={vitalAbbreviations[vitalName]}
        triggerProps={{
          'aria-label': `Web Vitals: ${vitalAbbreviations[vitalName]}`,
          prefix: t('Web Vitals'),
        }}
        position="bottom-start"
      />
    );
  }

  function renderError() {
    if (!error) {
      return null;
    }

    return (
      <Alert.Container>
        <Alert type="error">{error}</Alert>
      </Alert.Container>
    );
  }

  function renderContent(vital: WebVital) {
    const {location, organization, eventView, projects} = props;

    const {start, end, statsPeriod, environment, project} = eventView;

    const query = decodeScalar(location.query.query, '');
    const orgSlug = organization.slug;
    const localDateStart = start ? getUtcToLocalDateObject(start) : null;
    const localDateEnd = end ? getUtcToLocalDateObject(end) : null;
    const interval = getInterval(
      {start: localDateStart, end: localDateEnd, period: statsPeriod},
      'high'
    );
    const filterString = getTransactionSearchQuery(location);
    const summaryConditions = getSummaryConditions(filterString);

    return (
      <Fragment>
        <FilterActions>
          <PageFilterBar condensed>
            <ProjectPageFilter />
            <EnvironmentPageFilter />
            <DatePageFilter />
          </PageFilterBar>
          <StyledSearchBarWrapper>
            <TransactionSearchQueryBuilder
              projects={project}
              initialQuery={query}
              onSearch={handleSearch}
              searchSource="performance_vitals"
            />
          </StyledSearchBarWrapper>
        </FilterActions>
        <VitalChart
          organization={organization}
          query={query}
          project={project}
          environment={environment}
          start={localDateStart}
          end={localDateEnd}
          statsPeriod={statsPeriod}
          interval={interval}
        />
        <StyledVitalInfo>
          <VitalInfo
            orgSlug={orgSlug}
            location={location}
            vital={vital}
            project={project}
            environment={environment}
            start={start}
            end={end}
            statsPeriod={statsPeriod}
          />
        </StyledVitalInfo>

        <Teams provideUserTeams>
          {({teams, initiallyLoaded}) =>
            initiallyLoaded ? (
              <TeamKeyTransactionManager.Provider
                organization={organization}
                teams={teams}
                selectedTeams={['myteams']}
                selectedProjects={project.map(String)}
              >
                <Table
                  theme={theme}
                  eventView={eventView}
                  projects={projects}
                  organization={organization}
                  location={location}
                  setError={setError}
                  summaryConditions={summaryConditions}
                />
              </TeamKeyTransactionManager.Provider>
            ) : (
              <LoadingIndicator />
            )
          }
        </Teams>
      </Fragment>
    );
  }

  const {location, organization, vitalName} = props;

  const vital = vitalName || WebVital.LCP;

  return (
    <Fragment>
      <Layout.Header>
        <Layout.HeaderContent>
          <Breadcrumb organization={organization} location={location} vitalName={vital} />
          <Layout.Title>{vitalMap[vital]}</Layout.Title>
        </Layout.HeaderContent>
        <Layout.HeaderActions>
          <ButtonBar>
            {renderVitalSwitcher()}
            <Feature organization={organization} features="incidents">
              {({hasFeature}) =>
                hasFeature &&
                !deprecateTransactionAlerts(organization) &&
                renderCreateAlertButton()
              }
            </Feature>
          </ButtonBar>
        </Layout.HeaderActions>
      </Layout.Header>
      <Layout.Body>
        {renderError()}
        <Layout.Main fullWidth>
          <StyledDescription>{vitalDescription[vitalName]}</StyledDescription>
          <SupportedBrowsers>
            {Object.values(Browser).map(browser => (
              <BrowserItem key={browser}>
                {vitalSupportedBrowsers[vitalName]?.includes(browser) ? (
                  <IconCheckmark color="successText" size="sm" />
                ) : (
                  <IconClose color="dangerText" size="sm" />
                )}
                {browser}
              </BrowserItem>
            ))}
          </SupportedBrowsers>
          {renderContent(vital)}
        </Layout.Main>
      </Layout.Body>
    </Fragment>
  );
}

export default withProjects(VitalDetailContent);

const StyledDescription = styled('div')`
  font-size: ${p => p.theme.fontSize.md};
  margin-bottom: ${space(3)};
`;

const StyledVitalInfo = styled('div')`
  margin-bottom: ${space(3)};
`;

const SupportedBrowsers = styled('div')`
  display: inline-flex;
  gap: ${space(2)};
  margin-bottom: ${space(3)};
`;

const BrowserItem = styled('div')`
  display: flex;
  align-items: center;
  gap: ${space(1)};
`;

const FilterActions = styled('div')`
  display: grid;
  gap: ${space(2)};
  margin-bottom: ${space(2)};

  @media (min-width: ${p => p.theme.breakpoints.sm}) {
    grid-template-columns: auto 1fr;
  }
`;

const StyledSearchBarWrapper = styled('div')`
  @media (min-width: ${p => p.theme.breakpoints.sm}) {
    order: 1;
    grid-column: 1/6;
  }

  @media (min-width: ${p => p.theme.breakpoints.xl}) {
    order: initial;
    grid-column: auto;
  }
`;
