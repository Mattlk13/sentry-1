import ApiForm from 'sentry/components/forms/apiForm';
import MultipleCheckbox from 'sentry/components/forms/controls/multipleCheckbox';
import BooleanField from 'sentry/components/forms/fields/booleanField';
import TextField from 'sentry/components/forms/fields/textField';
import FormField from 'sentry/components/forms/formField';
import Panel from 'sentry/components/panels/panel';
import PanelBody from 'sentry/components/panels/panelBody';
import PanelHeader from 'sentry/components/panels/panelHeader';
import {t} from 'sentry/locale';
import type {ServiceHook} from 'sentry/types/integrations';
import type {Organization} from 'sentry/types/organization';
import normalizeUrl from 'sentry/utils/url/normalizeUrl';
import {useNavigate} from 'sentry/utils/useNavigate';

const EVENT_CHOICES = ['event.alert', 'event.created'];

type Props = {
  initialData: Partial<ServiceHook> & {isActive: boolean};
  organization: Organization;
  projectId: string;
  hookId?: string;
};

export default function ServiceHookSettingsForm({
  initialData,
  organization,
  projectId,
  hookId,
}: Props) {
  const navigate = useNavigate();

  const onSubmitSuccess = () => {
    navigate(normalizeUrl(`/settings/${organization.slug}/projects/${projectId}/hooks/`));
  };

  const endpoint = hookId
    ? `/projects/${organization.slug}/${projectId}/hooks/${hookId}/`
    : `/projects/${organization.slug}/${projectId}/hooks/`;

  return (
    <Panel>
      <ApiForm
        apiMethod={hookId ? 'PUT' : 'POST'}
        apiEndpoint={endpoint}
        initialData={initialData}
        onSubmitSuccess={onSubmitSuccess}
        footerStyle={{
          marginTop: 0,
          paddingRight: 20,
        }}
        submitLabel={hookId ? t('Save Changes') : t('Create Hook')}
      >
        <PanelHeader>{t('Hook Configuration')}</PanelHeader>
        <PanelBody>
          <BooleanField name="isActive" label={t('Active')} />
          <TextField
            name="url"
            label={t('URL')}
            required
            help={t('The URL which will receive events.')}
          />
          <FormField
            name="events"
            label={t('Events')}
            inline={false}
            help={t('The event types you wish to subscribe to.')}
          >
            {({name, value, onChange}: any) => (
              <MultipleCheckbox onChange={onChange} value={value} name={name}>
                {EVENT_CHOICES.map(event => (
                  <MultipleCheckbox.Item key={event} value={event}>
                    {event}
                  </MultipleCheckbox.Item>
                ))}
              </MultipleCheckbox>
            )}
          </FormField>
        </PanelBody>
      </ApiForm>
    </Panel>
  );
}
