import {Fragment} from 'react';

import {addErrorMessage} from 'sentry/actionCreators/indicator';
import {hasEveryAccess} from 'sentry/components/acl/access';
import {Link} from 'sentry/components/core/link';
import Form from 'sentry/components/forms/form';
import JsonForm from 'sentry/components/forms/jsonForm';
import SentryDocumentTitle from 'sentry/components/sentryDocumentTitle';
import projectSecurityAndPrivacyGroups from 'sentry/data/forms/projectSecurityAndPrivacyGroups';
import {t, tct} from 'sentry/locale';
import ProjectsStore from 'sentry/stores/projectsStore';
import type {Organization} from 'sentry/types/organization';
import type {Project} from 'sentry/types/project';
import {DataScrubbing} from 'sentry/views/settings/components/dataScrubbing';
import SettingsPageHeader from 'sentry/views/settings/components/settingsPageHeader';
import {ProjectPermissionAlert} from 'sentry/views/settings/project/projectPermissionAlert';

type Props = {
  organization: Organization;
  project: Project;
};

export default function ProjectSecurityAndPrivacy({organization, project}: Props) {
  function handleUpdateProject(data: Project) {
    // This will update our project global state
    ProjectsStore.onUpdateSuccess(data);
  }

  const initialData = project;
  const projectSlug = project.slug;
  const endpoint = `/projects/${organization.slug}/${projectSlug}/`;
  const features = new Set(organization.features);
  const relayPiiConfig = project.relayPiiConfig;
  const apiMethod = 'PUT';
  const title = t('Security & Privacy');

  const hasAccess = hasEveryAccess(['project:write'], {organization, project});

  return (
    <Fragment>
      <SentryDocumentTitle title={title} projectSlug={projectSlug} />
      <SettingsPageHeader title={title} />
      <ProjectPermissionAlert project={project} />

      <Form
        saveOnBlur
        allowUndo
        initialData={initialData}
        apiMethod={apiMethod}
        apiEndpoint={endpoint}
        onSubmitSuccess={handleUpdateProject}
        onSubmitError={() => addErrorMessage('Unable to save change')}
      >
        <JsonForm
          additionalFieldProps={{organization, project}}
          features={features}
          disabled={!hasAccess}
          forms={projectSecurityAndPrivacyGroups}
        />
      </Form>
      <DataScrubbing
        additionalContext={
          <span>
            {tct(
              'Advanced data scrubbing rules can be configured for each project. These rules will be applied in addition to any organization-level rules configured in [linkToOrganizationSecurityAndPrivacy].',
              {
                linkToOrganizationSecurityAndPrivacy: (
                  <Link to={`/settings/${organization.slug}/security-and-privacy/`}>
                    {title}
                  </Link>
                ),
              }
            )}
          </span>
        }
        endpoint={endpoint}
        relayPiiConfig={relayPiiConfig}
        disabled={!hasAccess}
        organization={organization}
        project={project}
        onSubmitSuccess={data => handleUpdateProject({...project, ...data})}
      />
    </Fragment>
  );
}
