import {ExternalLink} from 'sentry/components/core/link';
import type {
  Docs,
  DocsParams,
  OnboardingConfig,
} from 'sentry/components/onboarding/gettingStartedDoc/types';
import {StepType} from 'sentry/components/onboarding/gettingStartedDoc/types';
import {getUploadSourceMapsStep} from 'sentry/components/onboarding/gettingStartedDoc/utils';
import {
  getCrashReportJavaScriptInstallStep,
  getCrashReportModalConfigDescription,
  getCrashReportModalIntroduction,
} from 'sentry/components/onboarding/gettingStartedDoc/utils/feedbackOnboarding';
import {
  feedbackOnboardingJsLoader,
  replayOnboardingJsLoader,
} from 'sentry/gettingStartedDocs/javascript/jsLoader/jsLoader';
import {t, tct} from 'sentry/locale';
import {
  getImportInstrumentSnippet,
  getInstallConfig,
  getNodeAgentMonitoringOnboarding,
  getNodeProfilingOnboarding,
  getSdkInitSnippet,
  getSentryImportSnippet,
} from 'sentry/utils/gettingStartedDocs/node';

type Params = DocsParams;

const getSdkSetupSnippet = () => `
${getImportInstrumentSnippet()}

// All other imports below
${getSentryImportSnippet('node')}
const Fastify = require('fastify')

const app = Fastify();

Sentry.setupFastifyErrorHandler(app);

app.get("/", function rootHandler(req, res) {
  res.send("Hello world!");
});

app.listen(3000);
`;

const onboarding: OnboardingConfig = {
  introduction: () =>
    tct('In this quick guide you’ll use [strong:npm] or [strong:yarn] to set up:', {
      strong: <strong />,
    }),
  install: (params: Params) => [
    {
      type: StepType.INSTALL,
      description: t('Add the Sentry Node SDK as a dependency:'),
      configurations: getInstallConfig(params),
    },
  ],
  configure: (params: Params) => [
    {
      type: StepType.CONFIGURE,
      description: t(
        "Initialize Sentry as early as possible in your application's lifecycle."
      ),
      configurations: [
        {
          description: tct(
            'To initialize the SDK before everything else, create an external file called [code:instrument.js/mjs].',
            {code: <code />}
          ),
          code: [
            {
              label: 'JavaScript',
              value: 'javascript',
              language: 'javascript',
              filename: 'instrument.(js|mjs)',
              code: getSdkInitSnippet(params, 'node'),
            },
          ],
        },
        {
          description: tct(
            "Make sure to import [code:instrument.js/mjs] at the top of your file. Set up the error handler. This setup is typically done in your application's entry point file, which is usually [code:index.(js|ts)]. If you're running your application in ESM mode, or looking for alternative ways to set up Sentry, read about [docs:installation methods in our docs].",
            {
              code: <code />,
              docs: (
                <ExternalLink href="https://docs.sentry.io/platforms/javascript/guides/fastify/install/" />
              ),
            }
          ),
          code: [
            {
              label: 'JavaScript',
              value: 'javascript',
              language: 'javascript',
              filename: 'index.(js|mjs)',
              code: getSdkSetupSnippet(),
            },
          ],
        },
      ],
    },
    getUploadSourceMapsStep({
      guideLink: 'https://docs.sentry.io/platforms/javascript/guides/fastify/sourcemaps/',
      ...params,
    }),
  ],
  verify: () => [
    {
      type: StepType.VERIFY,
      description: t(
        "This snippet contains an intentional error and can be used as a test to make sure that everything's working as expected."
      ),
      configurations: [
        {
          language: 'javascript',
          code: `
          app.get("/debug-sentry", function mainHandler(req, res) {
            throw new Error("My first Sentry error!");
          });
          `,
        },
      ],
    },
  ],
  nextSteps: (params: Params) => {
    const steps = [];

    if (params.isLogsSelected) {
      steps.push({
        id: 'logs',
        name: t('Logging Integrations'),
        description: t(
          'Add logging integrations to automatically capture logs from your application.'
        ),
        link: 'https://docs.sentry.io/platforms/javascript/guides/fastify/logs/#integrations',
      });
    }

    return steps;
  },
};

const crashReportOnboarding: OnboardingConfig = {
  introduction: () => getCrashReportModalIntroduction(),
  install: (params: Params) => getCrashReportJavaScriptInstallStep(params),
  configure: () => [
    {
      type: StepType.CONFIGURE,
      description: getCrashReportModalConfigDescription({
        link: 'https://docs.sentry.io/platforms/javascript/guides/express/user-feedback/configuration/#crash-report-modal',
      }),
    },
  ],
  verify: () => [],
  nextSteps: () => [],
};

const docs: Docs = {
  onboarding,
  replayOnboardingJsLoader,
  crashReportOnboarding,
  feedbackOnboardingJsLoader,
  profilingOnboarding: getNodeProfilingOnboarding(),
  agentMonitoringOnboarding: getNodeAgentMonitoringOnboarding(),
};

export default docs;
