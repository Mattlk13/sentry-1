import omit from 'lodash/omit';

import {ExternalLink} from 'sentry/components/core/link';
import {AnnotatedText} from 'sentry/components/events/meta/annotatedText';
import Highlight from 'sentry/components/highlight';
import {t} from 'sentry/locale';
import type {BreadcrumbTypeHTTP} from 'sentry/types/breadcrumbs';
import {defined} from 'sentry/utils';

import Summary from './summary';

type Props = {
  breadcrumb: BreadcrumbTypeHTTP;
  searchTerm: string;
  meta?: Record<any, any>;
};

export function Http({breadcrumb, searchTerm, meta}: Props) {
  const {data} = breadcrumb;

  const renderUrl = (url: any) => {
    if (typeof url === 'string') {
      const content = <Highlight text={searchTerm}>{url}</Highlight>;
      return url.match(/^https?:\/\//) ? (
        <ExternalLink data-test-id="http-renderer-external-link" href={url}>
          {content}
        </ExternalLink>
      ) : (
        <span>{content}</span>
      );
    }

    try {
      return <Highlight text={searchTerm}>{JSON.stringify(url)}</Highlight>;
    } catch {
      return t('Invalid URL');
    }
  };

  return (
    <Summary
      kvData={data ? omit(data, ['method', 'url', 'status_code']) : data}
      meta={meta}
    >
      {meta?.data?.method?.[''] ? (
        <AnnotatedText value={data?.method} meta={meta?.data?.method?.['']} />
      ) : (
        defined(data?.method) && (
          <strong>
            <Highlight text={searchTerm}>{`${data?.method} `}</Highlight>
          </strong>
        )
      )}
      {meta?.data?.url?.[''] ? (
        <AnnotatedText value={data?.url} meta={meta?.data?.url?.['']} />
      ) : (
        defined(data?.url) && renderUrl(data?.url)
      )}
      {meta?.data?.status_code?.[''] ? (
        <AnnotatedText value={data?.status_code} meta={meta?.data?.status_code?.['']} />
      ) : (
        defined(data?.status_code) && (
          <Highlight
            data-test-id="http-renderer-status-code"
            text={searchTerm}
          >{` [${data?.status_code}]`}</Highlight>
        )
      )}
    </Summary>
  );
}
