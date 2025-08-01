import {renderWithOnboardingLayout} from 'sentry-test/onboarding/renderWithOnboardingLayout';
import {screen} from 'sentry-test/reactTestingLibrary';
import {textWithMarkupMatcher} from 'sentry-test/utils';

import {ProductSolution} from 'sentry/components/onboarding/gettingStartedDoc/types';

import docs from './go';

describe('go onboarding docs', function () {
  it('renders errors onboarding docs correctly', function () {
    renderWithOnboardingLayout(docs);

    // Renders main headings
    expect(screen.getByRole('heading', {name: 'Install'})).toBeInTheDocument();
    expect(screen.getByRole('heading', {name: 'Configure SDK'})).toBeInTheDocument();
    expect(screen.getByRole('heading', {name: 'Verify'})).toBeInTheDocument();
  });

  it('renders performance onboarding docs correctly', async function () {
    renderWithOnboardingLayout(docs, {
      selectedProducts: [ProductSolution.PERFORMANCE_MONITORING],
    });

    const elements = await screen.findAllByText(
      textWithMarkupMatcher(/TracesSampleRate/)
    );
    for (const element of elements) {
      expect(element).toBeInTheDocument();
    }
  });

  it('renders logs onboarding docs correctly', async function () {
    renderWithOnboardingLayout(docs, {
      selectedProducts: [ProductSolution.LOGS],
    });

    const elements = await screen.findAllByText(textWithMarkupMatcher(/EnableLogs/));
    for (const element of elements) {
      expect(element).toBeInTheDocument();
    }
  });

  it('renders performance and logs onboarding docs correctly', async function () {
    renderWithOnboardingLayout(docs, {
      selectedProducts: [ProductSolution.PERFORMANCE_MONITORING, ProductSolution.LOGS],
    });

    const traceElements = await screen.findAllByText(
      textWithMarkupMatcher(/TracesSampleRate/)
    );
    for (const element of traceElements) {
      expect(element).toBeInTheDocument();
    }

    const logElements = await screen.findAllByText(textWithMarkupMatcher(/EnableLogs/));
    for (const element of logElements) {
      expect(element).toBeInTheDocument();
    }
  });
});
