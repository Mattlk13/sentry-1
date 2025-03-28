import {type ReactNode, useCallback, useMemo} from 'react';
import styled from '@emotion/styled';
import type {Location} from 'history';

import Count from 'sentry/components/count';
import Duration from 'sentry/components/duration';
import GlobalSelectionLink from 'sentry/components/globalSelectionLink';
import type {GridColumnHeader, GridColumnOrder} from 'sentry/components/gridEditable';
import GridEditable from 'sentry/components/gridEditable';
import ProjectBadge from 'sentry/components/idBadge/projectBadge';
import renderSortableHeaderCell from 'sentry/components/replays/renderSortableHeaderCell';
import useQueryBasedColumnResize from 'sentry/components/replays/useQueryBasedColumnResize';
import useQueryBasedSorting from 'sentry/components/replays/useQueryBasedSorting';
import {Tooltip} from 'sentry/components/tooltip';
import {t} from 'sentry/locale';
import {space} from 'sentry/styles/space';
import type {AvatarProject} from 'sentry/types/project';
import type {ReleaseProject} from 'sentry/types/release';
import type {EventsMetaType} from 'sentry/utils/discover/eventView';
import {getFieldRenderer} from 'sentry/utils/discover/fieldRenderers';
import useOrganization from 'sentry/utils/useOrganization';
import {ReleaseProjectColumn} from 'sentry/views/releases/list/releaseCard';
import {getReleaseNewIssuesUrl} from 'sentry/views/releases/utils';

type ReleaseHealthItem = {
  adoption: number;
  adoption_stage: string;
  crash_free_sessions: number;
  date: string;
  error_count: number;
  lifespan: number | undefined;
  project: ReleaseProject;
  project_id: number;
  release: string;
  sessions: number;
};

interface Props {
  data: ReleaseHealthItem[];
  isError: boolean;
  isLoading: boolean;
  location: Location<any>;
  meta: EventsMetaType;
}

type Column = GridColumnHeader<keyof ReleaseHealthItem>;

const BASE_COLUMNS: Array<GridColumnOrder<keyof ReleaseHealthItem>> = [
  {key: 'release', name: 'release'},
  {key: 'project', name: 'project'},
  {key: 'date', name: 'date created'},
  {key: 'adoption', name: 'adoption'},
  {key: 'adoption_stage', name: 'stage'},
  {key: 'crash_free_sessions', name: 'crash free rate'},
  {key: 'sessions', name: 'total sessions'},
  {key: 'error_count', name: 'new issues'},
  {key: 'lifespan', name: 'lifespan'},
];

export default function ReleaseHealthTable({
  data,
  isError,
  isLoading,
  location,
  meta,
}: Props) {
  const {currentSort, makeSortLinkGenerator} = useQueryBasedSorting({
    defaultSort: {field: 'date', kind: 'desc'},
    location,
  });

  const {columns, handleResizeColumn} = useQueryBasedColumnResize({
    columns: BASE_COLUMNS,
    location,
  });

  const organization = useOrganization();

  const renderHeadCell = useMemo(
    () =>
      renderSortableHeaderCell({
        currentSort,
        makeSortLinkGenerator,
        onClick: () => {},
        rightAlignedColumns: [],
        sortableColumns: [],
      }),
    [currentSort, makeSortLinkGenerator]
  );

  const renderBodyCell = useCallback(
    (column: Column, dataRow: ReleaseHealthItem) => {
      const value = dataRow[column.key];

      if (column.key === 'lifespan') {
        return value === undefined ? (
          // the last lifespan in the table is rendered as '--' since there's nothing previous to compare it to
          '--'
        ) : (
          <CellWrapper>
            <Duration
              precision="hours"
              abbreviation
              seconds={(value as number) * (1 / 1000)}
            />
          </CellWrapper>
        );
      }

      if (column.key === 'adoption' || column.key === 'crash_free_sessions') {
        return `${(value as number).toFixed(2)}%`;
      }

      if (column.key === 'project') {
        return (
          <ReleaseProjectColumn>
            <ProjectBadge project={value as AvatarProject} avatarSize={16} />
          </ReleaseProjectColumn>
        );
      }

      if (column.key === 'error_count') {
        return (value as number) > 0 ? (
          <Tooltip title={t('Open in Issues')} position="auto-start">
            <GlobalSelectionLink
              to={getReleaseNewIssuesUrl(
                organization.slug,
                dataRow.project_id,
                dataRow.release
              )}
            >
              <Count value={value as number} />
            </GlobalSelectionLink>
          </Tooltip>
        ) : (
          <Count value={value as number} />
        );
      }
      if (!meta?.fields) {
        return value as ReactNode;
      }

      const renderer = getFieldRenderer(column.key, meta.fields, false);

      return (
        <CellWrapper>
          {renderer(dataRow, {
            location,
            organization,
            unit: meta.units?.[column.key],
          })}
        </CellWrapper>
      );
    },
    [organization, location, meta]
  );

  const tableEmptyMessage = (
    <MessageContainer>
      <Title>{t('No session health data was found')}</Title>
      <Subtitle>
        {t(
          'There was no session health data within this timeframe. Try expanding your timeframe or changing your global filters.'
        )}
      </Subtitle>
    </MessageContainer>
  );

  return (
    <GridEditable
      error={isError}
      isLoading={isLoading}
      data={data ?? []}
      columnOrder={columns}
      emptyMessage={tableEmptyMessage}
      columnSortBy={[]}
      stickyHeader
      grid={{
        onResizeColumn: handleResizeColumn,
        renderHeadCell,
        renderBodyCell: (column, row) => renderBodyCell(column, row),
      }}
    />
  );
}

const Subtitle = styled('div')`
  font-size: ${p => p.theme.fontSizeMedium};
`;

const Title = styled('div')`
  font-size: 24px;
`;

const MessageContainer = styled('div')`
  display: grid;
  grid-auto-flow: row;
  gap: ${space(1)};
  justify-items: center;
  text-align: center;
  padding: ${space(4)};
`;

const CellWrapper = styled('div')`
  & div {
    text-align: left;
  }
`;
