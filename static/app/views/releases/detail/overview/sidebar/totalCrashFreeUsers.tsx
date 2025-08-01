import styled from '@emotion/styled';
import type {Location} from 'history';
import pick from 'lodash/pick';
import moment from 'moment-timezone';

import Count from 'sentry/components/count';
import LoadingError from 'sentry/components/loadingError';
import LoadingIndicator from 'sentry/components/loadingIndicator';
import {normalizeDateTimeParams} from 'sentry/components/organizations/pageFilters/parse';
import * as SidebarSection from 'sentry/components/sidebarSection';
import {URL_PARAM} from 'sentry/constants/pageFilters';
import {t, tn} from 'sentry/locale';
import {space} from 'sentry/styles/space';
import type {Organization} from 'sentry/types/organization';
import type {CrashFreeTimeBreakdown} from 'sentry/types/release';
import {defined} from 'sentry/utils';
import {useApiQuery} from 'sentry/utils/queryClient';
import {displayCrashFreePercent} from 'sentry/views/releases/utils';

type Props = {
  location: Location;
  organization: Organization;
  projectSlug: string;
  version: string;
};

type ReleaseStatsType = {usersBreakdown: CrashFreeTimeBreakdown} | null;

function TotalCrashFreeUsers({location, organization, projectSlug, version}: Props) {
  const {
    data: releaseStats,
    isPending,
    isError,
  } = useApiQuery<ReleaseStatsType>(
    [
      `/projects/${organization.slug}/${projectSlug}/releases/${encodeURIComponent(
        version
      )}/stats/`,
      {
        query: {
          ...normalizeDateTimeParams(
            pick(location.query, [URL_PARAM.PROJECT, URL_PARAM.ENVIRONMENT])
          ),
          type: 'sessions',
        },
      },
    ],
    {staleTime: 0}
  );

  if (isPending) {
    return <LoadingIndicator />;
  }

  if (isError) {
    return <LoadingError />;
  }

  const crashFreeTimeBreakdown = releaseStats?.usersBreakdown;

  if (!crashFreeTimeBreakdown?.length) {
    return null;
  }

  const timeline = crashFreeTimeBreakdown
    .map(({date, crashFreeUsers, totalUsers}, index, data) => {
      // count number of crash free users from knowing percent and total
      const crashFreeUserCount = Math.round(((crashFreeUsers ?? 0) * totalUsers) / 100);
      // first item of timeline is release creation date, then we want to have relative date label
      const dateLabel =
        index === 0
          ? t('Release created')
          : `${moment(data[0]!.date).from(date, true)} ${t('later')}`;

      return {date: moment(date), dateLabel, crashFreeUsers, crashFreeUserCount};
    })
    // remove those timeframes that are in the future
    .filter(item => item.date.isBefore())
    // we want timeline to go from bottom to up
    .reverse();

  if (!timeline.length) {
    return null;
  }

  return (
    <SidebarSection.Wrap>
      <SidebarSection.Title>{t('Total Crash Free Users')}</SidebarSection.Title>
      <SidebarSection.Content>
        <Timeline>
          {timeline.map(row => (
            <Row key={row.date.toISOString()}>
              <InnerRow>
                <Text bold>{row.date.format('MMMM D')}</Text>
                <Text bold right>
                  <Count value={row.crashFreeUserCount} />{' '}
                  {tn('user', 'users', row.crashFreeUserCount)}
                </Text>
              </InnerRow>
              <InnerRow>
                <Text>{row.dateLabel}</Text>
                <Percent right>
                  {defined(row.crashFreeUsers)
                    ? displayCrashFreePercent(row.crashFreeUsers)
                    : '-'}
                </Percent>
              </InnerRow>
            </Row>
          ))}
        </Timeline>
      </SidebarSection.Content>
    </SidebarSection.Wrap>
  );
}

const Timeline = styled('div')`
  font-size: ${p => p.theme.fontSize.md};
  line-height: 1.2;
`;

const DOT_SIZE = 10;
const Row = styled('div')`
  border-left: 1px solid ${p => p.theme.border};
  padding-left: ${space(2)};
  padding-bottom: ${space(1)};
  margin-left: ${space(1)};
  position: relative;

  &:before {
    content: '';
    width: ${DOT_SIZE}px;
    height: ${DOT_SIZE}px;
    border-radius: 100%;
    background-color: ${p => p.theme.purple300};
    position: absolute;
    top: 0;
    left: -${Math.floor(DOT_SIZE / 2)}px;
  }

  &:last-child {
    border-left: 0;
  }
`;
const InnerRow = styled('div')`
  display: grid;
  grid-column-gap: ${space(2)};
  grid-auto-flow: column;
  grid-auto-columns: 1fr;

  padding-bottom: ${space(0.5)};
`;

const Text = styled('div')<{bold?: boolean; right?: boolean}>`
  text-align: ${p => (p.right ? 'right' : 'left')};
  color: ${p => (p.bold ? p.theme.textColor : p.theme.subText)};
  padding-bottom: ${space(0.25)};
  ${p => p.theme.overflowEllipsis};
`;

const Percent = styled(Text)`
  font-variant-numeric: tabular-nums;
`;

export default TotalCrashFreeUsers;
