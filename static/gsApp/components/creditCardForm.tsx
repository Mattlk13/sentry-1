import {useEffect, useRef, useState} from 'react';
import {css, useTheme} from '@emotion/react';
import styled from '@emotion/styled';

import rubikFontPath from 'sentry/../fonts/rubik-regular.woff';
import {Alert} from 'sentry/components/core/alert';
import {Button} from 'sentry/components/core/button';
import {ButtonBar} from 'sentry/components/core/button/buttonBar';
import {Input} from 'sentry/components/core/input';
import {ExternalLink} from 'sentry/components/core/link';
import FieldGroup from 'sentry/components/forms/fieldGroup';
import LoadingIndicator from 'sentry/components/loadingIndicator';
import {NODE_ENV} from 'sentry/constants';
import {t, tct} from 'sentry/locale';
import ConfigStore from 'sentry/stores/configStore';
import {space} from 'sentry/styles/space';

import type {FTCConsentLocation} from 'getsentry/types';
import {loadStripe} from 'getsentry/utils/stripe';

export type SubmitData = {
  /**
   * The card element used to collect the credit card.
   */
  cardElement: stripe.elements.Element;
  /**
   * To be called when the stripe operation is complete.
   * When called it re-enables the form buttons.
   */
  onComplete: () => void;
  /**
   * Stripe client instance used.
   */
  stripe: stripe.Stripe;
  /**
   * Validation errors from fields contained in this form.
   * If not-empty submission should not continue.
   */
  validationErrors: string[];
};

type Props = {
  /**
   * Handle the card form submission.
   */
  onSubmit: (data: SubmitData) => void;
  /**
   * budget mode text for fine print, if any.
   */
  budgetModeText?: string;
  /**
   * Text for the submit button.
   */
  buttonText?: string;
  /**
   * Text for the cancel button.
   */
  cancelButtonText?: string;
  /**
   * Classname/styled component wrapper for the form.
   */
  className?: string;
  /**
   * Error message to show.
   */
  error?: string;
  /**
   * If the error message has an action that can be retried, this callback
   * will be invoked by the 'retry' button shown in the error message.
   */
  errorRetry?: () => void;
  /**
   * Classname for the footer buttons.
   */
  footerClassName?: string;
  /**
   * Location of form, if any.
   */
  location?: FTCConsentLocation;
  /**
   * Handler for cancellation.
   */
  onCancel?: () => void;
  /**
   * The URL referrer, if any.
   */
  referrer?: string;
};

/**
 * Standalone credit card form that requires onSubmit to be handled
 * by the parent. This allows us to reuse the same form for both paymentintent, setupintent
 * and classic card flows.
 */
function CreditCardForm({
  className,
  error,
  errorRetry,
  onCancel,
  onSubmit,
  buttonText = t('Save Changes'),
  cancelButtonText = t('Cancel'),
  footerClassName = 'form-actions',
  referrer,
  location,
  budgetModeText,
}: Props) {
  const theme = useTheme();
  const [busy, setBusy] = useState(false);
  const [stripe, setStripe] = useState<stripe.Stripe>();
  const [cardElement, setCardElement] = useState<stripe.elements.Element>();
  const stripeMount = useRef<HTMLDivElement>(null);

  // XXX: Default loading to false when in test mode. The stripe elements will
  // never load, but we still want to test some functionality of this modal.
  const defaultLoadState = NODE_ENV !== 'test';

  const [loading, setLoading] = useState(defaultLoadState);

  useEffect(() => {
    loadStripe(Stripe => {
      const apiKey = ConfigStore.get('getsentry.stripePublishKey');
      const instance = Stripe(apiKey);
      setStripe(instance);
    });
  }, []);

  useEffect(() => {
    if (!stripe || !stripeMount.current) {
      return;
    }
    const stripeElementStyles = {
      base: {
        backgroundColor: theme.isChonk
          ? theme.tokens.background.primary
          : theme.background,
        color: theme.isChonk ? theme.tokens.content.primary : theme.textColor,
        fontFamily: theme.text.family,
        fontWeight: 400,
        fontSize: theme.fontSize.lg,
        '::placeholder': {
          color: theme.isChonk ? theme.tokens.content.muted : theme.gray300,
        },
        iconColor: theme.isChonk ? theme.tokens.content.primary : theme.gray300,
      },
      invalid: {
        color: theme.isChonk ? theme.tokens.content.danger : theme.red300,
        iconColor: theme.isChonk ? theme.tokens.content.danger : theme.red300,
      },
    };

    const stripeElements = stripe.elements({
      fonts: [{family: 'Rubik', src: `url(${rubikFontPath})`, weight: '400'}],
    });
    const stripeCardElement = stripeElements.create('card', {
      style: stripeElementStyles,
    });

    stripeCardElement.mount(stripeMount.current);
    stripeCardElement.on('ready', () => {
      setLoading(false);
    });
    setCardElement(stripeCardElement);
  }, [stripe, theme]);

  function onComplete() {
    setBusy(false);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) {
      return;
    }
    setBusy(true);

    const validationErrors: string[] = [];

    if (!stripe || !cardElement) {
      return;
    }
    onSubmit({stripe, cardElement, onComplete, validationErrors});
  }

  function handleCancel(e: React.MouseEvent) {
    e.preventDefault();
    if (busy) {
      return;
    }
    onCancel?.();
  }

  function handleErrorRetry(event: React.MouseEvent) {
    event.preventDefault();
    errorRetry?.();
  }

  const disabled = busy || loading;

  return (
    <form
      className={className}
      action="."
      method="POST"
      id="payment-form"
      onSubmit={handleSubmit}
    >
      {error && (
        <Alert.Container>
          <Alert type="error" showIcon={false}>
            <AlertContent>
              {error}
              {errorRetry && (
                <Button size="sm" onClick={handleErrorRetry}>
                  {t('Retry')}
                </Button>
              )}
            </AlertContent>
          </Alert>
        </Alert.Container>
      )}
      {loading && <LoadingIndicator />}
      {referrer?.includes('billing-failure') && (
        <Alert.Container>
          <Alert type="warning" showIcon={false}>
            {t('Your credit card will be charged upon update.')}
          </Alert>
        </Alert.Container>
      )}
      <CreditCardInfoWrapper isLoading={loading}>
        <StyledField
          stacked
          flexibleControlStateSize
          inline={false}
          label={t('Card Details')}
        >
          <FormControl>
            <div ref={stripeMount} />
          </FormControl>
        </StyledField>

        <Info>
          <small>
            {tct('Payments are processed securely through [stripe:Stripe].', {
              stripe: <ExternalLink href="https://stripe.com/" />,
            })}
          </small>
          {location !== null && location !== undefined && (
            <FinePrint>
              {tct(
                'By clicking [buttonText], you authorize Sentry to automatically charge you recurring subscription fees and applicable [budgetModeText] fees. Recurring charges occur at the start of your selected billing cycle for subscription fees and monthly for [budgetModeText] fees. You may cancel your subscription at any time [here:here].',
                {
                  buttonText: <b>{buttonText}</b>,
                  budgetModeText,
                  here: (
                    <ExternalLink href="https://sentry.io/settings/billing/cancel/" />
                  ),
                }
              )}
            </FinePrint>
          )}
        </Info>

        <div className={footerClassName}>
          <StyledButtonBar>
            {onCancel && (
              <Button
                data-test-id="cancel"
                priority="default"
                disabled={disabled}
                onClick={handleCancel}
              >
                {cancelButtonText}
              </Button>
            )}
            <Button
              data-test-id="submit"
              type="submit"
              priority="primary"
              disabled={disabled}
              onClick={handleSubmit}
            >
              {buttonText}
            </Button>
          </StyledButtonBar>
        </div>
      </CreditCardInfoWrapper>
    </form>
  );
}

const FormControl = styled(Input.withComponent('div'))`
  /* Allow stripe form element to fill whatever height it needs to based
   * on the config that we are providing it with. */
  height: ${p => (p.theme.isChonk ? 'auto' : undefined)};
`;

const fieldCss = css`
  padding-right: 0;
  padding-left: 0;
`;

const StyledField = styled(FieldGroup)`
  ${fieldCss};
  padding-top: 0;
  height: auto;
`;

const Info = styled('div')`
  ${fieldCss};
  margin-bottom: ${space(3)};
  margin-top: ${space(1)};
`;

const FinePrint = styled('div')`
  margin-top: ${space(1)};
  font-size: ${p => p.theme.fontSize.xs};
  color: ${p => (p.theme.isChonk ? p.theme.tokens.content.muted : p.theme.gray300)};
`;

const CreditCardInfoWrapper = styled('div')<{isLoading?: boolean}>`
  ${p => p.isLoading && 'display: none'};
`;

const StyledButtonBar = styled(ButtonBar)`
  max-width: fit-content;
`;

const AlertContent = styled('span')`
  display: flex;
  align-items: center;
  justify-content: space-between;
`;

export default CreditCardForm;
