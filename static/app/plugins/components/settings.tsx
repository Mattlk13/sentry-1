import {css} from '@emotion/react';
import styled from '@emotion/styled';
import isEqual from 'lodash/isEqual';

import {Alert} from 'sentry/components/core/alert';
import {LinkButton} from 'sentry/components/core/button/linkButton';
import Form from 'sentry/components/deprecatedforms/form';
import FormState from 'sentry/components/forms/state';
import LoadingIndicator from 'sentry/components/loadingIndicator';
import {t, tct} from 'sentry/locale';
import PluginComponentBase from 'sentry/plugins/pluginComponentBase';
import type {Plugin} from 'sentry/types/integrations';
import type {Organization} from 'sentry/types/organization';
import type {Project} from 'sentry/types/project';
import type {IntegrationAnalyticsKey} from 'sentry/utils/analytics/integrations';
import {parseRepo} from 'sentry/utils/git/parseRepo';
import {trackIntegrationAnalytics} from 'sentry/utils/integrationUtil';

type Props = {
  organization: Organization;
  plugin: Plugin;
  project: Project;
} & PluginComponentBase['props'];

type Field = Parameters<typeof PluginComponentBase.prototype.renderField>[0]['config'];

type BackendField = Field & {defaultValue?: any; value?: any};

type State = {
  errors: Record<string, any>;
  fieldList: Field[] | null;
  formData: Record<string, any>;
  initialData: Record<string, any> | null;
  rawData: Record<string, any>;
  wasConfiguredOnPageLoad: boolean;
} & PluginComponentBase['state'];

class PluginSettings<
  P extends Props = Props,
  S extends State = State,
> extends PluginComponentBase<P, S> {
  constructor(props: P) {
    super(props);

    Object.assign(this.state, {
      fieldList: null,
      initialData: null,
      formData: null,
      errors: {},
      rawData: {},
      // override default FormState.READY if api requests are
      // necessary to even load the form
      state: FormState.LOADING,
      wasConfiguredOnPageLoad: false,
    });
  }

  trackPluginEvent = (eventKey: IntegrationAnalyticsKey) => {
    trackIntegrationAnalytics(eventKey, {
      integration: this.props.plugin.id,
      integration_type: 'plugin',
      view: 'plugin_details',
      already_installed: this.state.wasConfiguredOnPageLoad,
      organization: this.props.organization,
    });
  };

  componentDidMount() {
    this.fetchData();
  }

  getPluginEndpoint() {
    const org = this.props.organization;
    const project = this.props.project;
    return `/projects/${org.slug}/${project.slug}/plugins/${this.props.plugin.id}/`;
  }

  changeField(name: string, value: any) {
    const formData: State['formData'] = this.state.formData;
    formData[name] = value;
    // upon changing a field, remove errors
    const errors = this.state.errors;
    delete errors[name];
    this.setState({formData, errors});
  }

  onSubmit() {
    if (!this.state.wasConfiguredOnPageLoad) {
      // Users cannot install plugins like other integrations but we need the events for the funnel
      // we will treat a user saving a plugin that wasn't already configured as an installation event
      this.trackPluginEvent('integrations.installation_start');
    }

    let repo = this.state.formData.repo;
    repo = repo && parseRepo(repo);
    const parsedFormData = {...this.state.formData, repo};
    this.api.request(this.getPluginEndpoint(), {
      data: parsedFormData,
      method: 'PUT',
      success: this.onSaveSuccess.bind(this, (data: any) => {
        const formData = {};
        const initialData = {};
        data.config.forEach((field: any) => {
          // @ts-expect-error TS(7053): Element implicitly has an 'any' type because expre... Remove this comment to see the full error message
          formData[field.name] = field.value || field.defaultValue;
          // @ts-expect-error TS(7053): Element implicitly has an 'any' type because expre... Remove this comment to see the full error message
          initialData[field.name] = field.value;
        });
        this.setState({
          fieldList: data.config,
          formData,
          initialData,
          errors: {},
        });
        this.trackPluginEvent('integrations.config_saved');

        if (!this.state.wasConfiguredOnPageLoad) {
          this.trackPluginEvent('integrations.installation_complete');
        }
      }),
      error: this.onSaveError.bind(this, (error: any) => {
        this.setState({
          errors: error.responseJSON?.errors || {},
        });
      }),
      complete: this.onSaveComplete,
    });
  }

  fetchData() {
    this.api.request(this.getPluginEndpoint(), {
      success: data => {
        if (!data.config) {
          this.setState(
            {
              rawData: data,
            },
            this.onLoadSuccess
          );
          return;
        }
        let wasConfiguredOnPageLoad = false;
        const formData = {};
        const initialData = {};
        data.config.forEach((field: BackendField) => {
          // @ts-expect-error TS(7053): Element implicitly has an 'any' type because expre... Remove this comment to see the full error message
          formData[field.name] = field.value || field.defaultValue;
          // @ts-expect-error TS(7053): Element implicitly has an 'any' type because expre... Remove this comment to see the full error message
          initialData[field.name] = field.value;
          // for simplicity sake, we will consider a plugin was configured if we have any value that is stored in the DB
          wasConfiguredOnPageLoad = wasConfiguredOnPageLoad || !!field.value;
        });
        this.setState(
          {
            fieldList: data.config,
            formData,
            initialData,
            wasConfiguredOnPageLoad,
            // call this here to prevent FormState.READY from being
            // set before fieldList is
          },
          this.onLoadSuccess
        );
      },
      error: this.onLoadError,
    });
  }

  render() {
    if (this.state.state === FormState.LOADING) {
      return <LoadingIndicator />;
    }
    const isSaving = this.state.state === FormState.SAVING;
    const hasChanges = !isEqual(this.state.initialData, this.state.formData);

    const data = this.state.rawData;
    if (data.config_error) {
      let authUrl = data.auth_url;
      if (authUrl.includes('?')) {
        authUrl += '&next=' + encodeURIComponent(document.location.pathname);
      } else {
        authUrl += '?next=' + encodeURIComponent(document.location.pathname);
      }
      return (
        <div className="m-b-1">
          <Alert.Container>
            <Alert type="warning" showIcon={false}>
              {data.config_error}
            </Alert>
          </Alert.Container>
          <LinkButton priority="primary" href={authUrl}>
            {t('Associate Identity')}
          </LinkButton>
        </div>
      );
    }

    if (this.state.state === FormState.ERROR && !this.state.fieldList) {
      return (
        <Alert.Container>
          <Alert type="error" showIcon={false}>
            {tct(
              'An unknown error occurred. Need help with this? [link:Contact support]',
              {
                link: <a href="https://sentry.io/support/" />,
              }
            )}
          </Alert>
        </Alert.Container>
      );
    }

    const fieldList: State['fieldList'] = this.state.fieldList;

    if (!fieldList?.length) {
      return null;
    }
    return (
      <Form
        css={css`
          width: 100%;
        `}
        onSubmit={this.onSubmit}
        submitDisabled={isSaving || !hasChanges}
      >
        <Flex>
          {this.state.errors.__all__ && (
            <Alert type="error" showIcon={false}>
              <ul>
                <li>{this.state.errors.__all__}</li>
              </ul>
            </Alert>
          )}
          {this.state.fieldList?.map(f =>
            this.renderField({
              config: f,
              formData: this.state.formData,
              formErrors: this.state.errors,
              onChange: this.changeField.bind(this, f.name),
            })
          )}
        </Flex>
      </Form>
    );
  }
}

const Flex = styled('div')`
  display: flex;
  flex-direction: column;
`;

export default PluginSettings;
