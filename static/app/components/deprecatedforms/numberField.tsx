import InputField from 'sentry/components/deprecatedforms/inputField';
import withFormContext from 'sentry/components/deprecatedforms/withFormContext';

type Props = {
  max?: number;
  min?: number;
} & InputField['props'];

// XXX: This is ONLY used in GenericField. If we can delete that this can go.

/**
 * @deprecated Do not use this
 */
export class NumberField extends InputField<Props> {
  coerceValue(value: any) {
    const intValue = parseInt(value, 10);

    // return previous value if new value is NaN, otherwise, will get recursive error
    const isNewCoercedNaN = isNaN(intValue);

    if (!isNewCoercedNaN) {
      return intValue;
    }

    return '';
  }

  getType() {
    return 'number';
  }

  getAttributes() {
    return {
      min: this.props.min || undefined,
      max: this.props.max || undefined,
    };
  }
}

/**
 * @deprecated Do not use this
 */
export default withFormContext(NumberField);
