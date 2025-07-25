import {Component, createRef, Fragment} from 'react';
import styled from '@emotion/styled';

import TextField from 'sentry/components/forms/fields/textField';
import TextOverflow from 'sentry/components/textOverflow';
import {t} from 'sentry/locale';
import {space} from 'sentry/styles/space';
import {defined} from 'sentry/utils';
import type {SourceSuggestion} from 'sentry/views/settings/components/dataScrubbing/types';
import {SourceSuggestionType} from 'sentry/views/settings/components/dataScrubbing/types';
import {
  binarySuggestions,
  unarySuggestions,
} from 'sentry/views/settings/components/dataScrubbing/utils';

import SourceSuggestionExamples from './sourceSuggestionExamples';

const defaultHelp = t(
  'Where to look. In the simplest case this can be an attribute name.'
);

type Props = {
  isRegExMatchesSelected: boolean;
  onChange: (value: string) => void;
  suggestions: SourceSuggestion[];
  value: string;
  error?: string;
  onBlur?: (value: string, event: React.FocusEvent<HTMLInputElement>) => void;
};

type State = {
  activeSuggestion: number;
  fieldValues: Array<SourceSuggestion | SourceSuggestion[]>;
  help: string;
  hideCaret: boolean;
  showSuggestions: boolean;
  suggestions: SourceSuggestion[];
};

class SourceField extends Component<Props, State> {
  state: State = {
    suggestions: [],
    fieldValues: [],
    activeSuggestion: 0,
    showSuggestions: false,
    hideCaret: false,
    help: defaultHelp,
  };

  componentDidMount() {
    this.loadFieldValues(this.props.value);
    this.toggleSuggestions(false);
  }

  componentDidUpdate(prevProps: Props) {
    if (prevProps.suggestions !== this.props.suggestions) {
      this.loadFieldValues(this.props.value);
      this.toggleSuggestions(false);
    }

    if (
      prevProps.isRegExMatchesSelected !== this.props.isRegExMatchesSelected ||
      prevProps.value !== this.props.value
    ) {
      this.checkPossiblyRegExMatchExpression(this.props.value);
    }
  }

  selectorField = createRef<HTMLDivElement>();
  suggestionList = createRef<HTMLUListElement>();

  getAllSuggestions() {
    return [...this.getValueSuggestions(), ...unarySuggestions, ...binarySuggestions];
  }

  getValueSuggestions() {
    return this.props.suggestions || [];
  }

  getFilteredSuggestions(value: string, type: SourceSuggestionType) {
    let valuesToBeFiltered: SourceSuggestion[] = [];

    switch (type) {
      case SourceSuggestionType.BINARY: {
        valuesToBeFiltered = binarySuggestions;
        break;
      }
      case SourceSuggestionType.VALUE: {
        valuesToBeFiltered = this.getValueSuggestions();
        break;
      }
      case SourceSuggestionType.UNARY: {
        valuesToBeFiltered = unarySuggestions;
        break;
      }
      default: {
        valuesToBeFiltered = [...this.getValueSuggestions(), ...unarySuggestions];
      }
    }

    const filteredSuggestions = valuesToBeFiltered.filter(s =>
      s.value.toLowerCase().includes(value.toLowerCase())
    );

    return filteredSuggestions;
  }

  // @ts-expect-error TS(7023): 'getNewSuggestions' implicitly has return type 'an... Remove this comment to see the full error message
  getNewSuggestions(fieldValues: Array<SourceSuggestion | SourceSuggestion[]>) {
    const lastFieldValue = fieldValues[fieldValues.length - 1]!;
    const penultimateFieldValue = fieldValues[fieldValues.length - 2]!;

    if (Array.isArray(lastFieldValue)) {
      // recursion
      return this.getNewSuggestions(lastFieldValue);
    }

    if (Array.isArray(penultimateFieldValue)) {
      if (lastFieldValue?.type === 'binary') {
        // returns filtered values
        return this.getFilteredSuggestions(
          lastFieldValue?.value,
          SourceSuggestionType.VALUE
        );
      }
      // returns all binaries without any filter
      return this.getFilteredSuggestions('', SourceSuggestionType.BINARY);
    }

    if (lastFieldValue?.type === 'value' && penultimateFieldValue?.type === 'unary') {
      // returns filtered values
      return this.getFilteredSuggestions(
        lastFieldValue?.value,
        SourceSuggestionType.VALUE
      );
    }

    if (lastFieldValue?.type === 'unary') {
      // returns all values without any filter
      return this.getFilteredSuggestions('', SourceSuggestionType.VALUE);
    }

    if (lastFieldValue?.type === 'string' && penultimateFieldValue?.type === 'value') {
      // returns all binaries without any filter
      return this.getFilteredSuggestions('', SourceSuggestionType.BINARY);
    }

    if (
      lastFieldValue?.type === 'string' &&
      penultimateFieldValue?.type === 'string' &&
      !penultimateFieldValue?.value
    ) {
      // returns all values without any filter
      return this.getFilteredSuggestions('', SourceSuggestionType.STRING);
    }

    if (
      (penultimateFieldValue?.type === 'string' && !lastFieldValue?.value) ||
      (penultimateFieldValue?.type === 'value' && !lastFieldValue?.value) ||
      lastFieldValue?.type === 'binary'
    ) {
      // returns filtered binaries
      return this.getFilteredSuggestions(
        lastFieldValue?.value,
        SourceSuggestionType.BINARY
      );
    }

    return this.getFilteredSuggestions(lastFieldValue?.value, lastFieldValue?.type);
  }

  loadFieldValues(newValue: string) {
    const fieldValues: Array<SourceSuggestion | SourceSuggestion[]> = [];

    const splittedValue = newValue.split(' ');

    for (const value of splittedValue) {
      const lastFieldValue = fieldValues[fieldValues.length - 1]!;

      if (
        lastFieldValue &&
        !Array.isArray(lastFieldValue) &&
        !lastFieldValue.value &&
        !value
      ) {
        continue;
      }

      if (value.includes('!') && !!value.split('!')[1]) {
        const valueAfterUnaryOperator = value.split('!')[1]!;
        const selector = this.getAllSuggestions().find(
          s => s.value === valueAfterUnaryOperator
        );
        if (!selector) {
          fieldValues.push([
            unarySuggestions[0]!,
            {type: SourceSuggestionType.STRING, value: valueAfterUnaryOperator},
          ]);
          continue;
        }
        fieldValues.push([unarySuggestions[0]!, selector]);
        continue;
      }

      const selector = this.getAllSuggestions().find(s => s.value === value);
      if (selector) {
        fieldValues.push(selector);
        continue;
      }

      fieldValues.push({type: SourceSuggestionType.STRING, value});
    }

    const filteredSuggestions = this.getNewSuggestions(fieldValues);

    this.setState({
      fieldValues,
      activeSuggestion: 0,
      suggestions: filteredSuggestions,
    });
  }

  scrollToSuggestion() {
    const {activeSuggestion, hideCaret} = this.state;

    this.suggestionList?.current?.children[activeSuggestion]!.scrollIntoView({
      behavior: 'smooth',
      block: 'nearest',
      inline: 'start',
    });

    if (!hideCaret) {
      this.setState({
        hideCaret: true,
      });
    }
  }

  changeParentValue() {
    const {onChange} = this.props;
    const {fieldValues} = this.state;
    const newValue: string[] = [];

    for (const fieldValue of fieldValues) {
      if (Array.isArray(fieldValue)) {
        if (fieldValue[0]?.value || fieldValue[1]?.value) {
          newValue.push(`${fieldValue[0]?.value ?? ''}${fieldValue[1]?.value ?? ''}`);
        }
        continue;
      }
      newValue.push(fieldValue.value);
    }

    onChange(newValue.join(' '));
  }

  getNewFieldValues(
    suggestion: SourceSuggestion
  ): Array<SourceSuggestion | SourceSuggestion[]> {
    const fieldValues = [...this.state.fieldValues];
    const lastFieldValue = fieldValues[fieldValues.length - 1]!;

    if (!defined(lastFieldValue)) {
      return [suggestion];
    }

    if (Array.isArray(lastFieldValue)) {
      fieldValues[fieldValues.length - 1] = [lastFieldValue[0]!, suggestion];
      return fieldValues;
    }

    if (lastFieldValue?.type === 'unary') {
      fieldValues[fieldValues.length - 1] = [lastFieldValue, suggestion];
    }

    if (lastFieldValue?.type === 'string' && !lastFieldValue?.value) {
      fieldValues[fieldValues.length - 1] = suggestion;
      return fieldValues;
    }

    if (suggestion.type === 'value' && lastFieldValue?.value !== suggestion.value) {
      return [suggestion];
    }

    return fieldValues;
  }

  checkPossiblyRegExMatchExpression(value: string) {
    const {isRegExMatchesSelected} = this.props;
    const {help} = this.state;

    if (isRegExMatchesSelected) {
      if (help) {
        this.setState({help: ''});
      }
      return;
    }

    const isMaybeRegExp = new RegExp('^/.*/g?$').test(value);

    if (help) {
      if (!isMaybeRegExp) {
        this.setState({
          help: defaultHelp,
        });
      }
      return;
    }

    if (isMaybeRegExp) {
      this.setState({
        help: t("You might want to change Data Type's value to 'Regex matches'"),
      });
    }
  }

  toggleSuggestions(showSuggestions: boolean) {
    this.setState({showSuggestions});
  }

  handleChange = (value: string) => {
    this.loadFieldValues(value);
    this.props.onChange(value);
  };

  handleClickOutside = () => {
    this.setState({
      showSuggestions: false,
      hideCaret: false,
    });
  };

  handleClickSuggestionItem = (suggestion: SourceSuggestion) => {
    const fieldValues = this.getNewFieldValues(suggestion);
    this.setState(
      {
        fieldValues,
        activeSuggestion: 0,
        showSuggestions: false,
        hideCaret: false,
      },
      this.changeParentValue
    );
  };

  handleKeyDown = (_value: string, event: React.KeyboardEvent<HTMLInputElement>) => {
    event.persist();

    const {key} = event;
    const {activeSuggestion, suggestions} = this.state;

    if (key === 'Backspace' || key === ' ') {
      this.toggleSuggestions(true);
      return;
    }

    if (key === 'Enter') {
      this.handleClickSuggestionItem(suggestions[activeSuggestion]!);
      return;
    }

    if (key === 'ArrowUp') {
      if (activeSuggestion === 0) {
        return;
      }
      this.setState({activeSuggestion: activeSuggestion - 1}, () => {
        this.scrollToSuggestion();
      });
      return;
    }

    if (key === 'ArrowDown') {
      if (activeSuggestion === suggestions.length - 1) {
        return;
      }
      this.setState({activeSuggestion: activeSuggestion + 1}, () => {
        this.scrollToSuggestion();
      });
      return;
    }
  };

  handleFocus = () => {
    this.toggleSuggestions(true);
  };

  render() {
    const {error, value, onBlur} = this.props;
    const {showSuggestions, suggestions, activeSuggestion, hideCaret, help} = this.state;

    return (
      <Wrapper ref={this.selectorField} hideCaret={hideCaret}>
        <StyledTextField
          data-test-id="source-field"
          label={t('Source')}
          name="source"
          placeholder={t('Enter a custom attribute, variable or header name')}
          onChange={this.handleChange}
          autoComplete="off"
          value={value}
          error={error}
          help={help}
          onKeyDown={this.handleKeyDown}
          onBlur={onBlur}
          onFocus={this.handleFocus}
          inline={false}
          flexibleControlStateSize
          stacked
          required
          showHelpInTooltip
        />
        {showSuggestions && suggestions.length > 0 && (
          <Fragment>
            <Suggestions
              ref={this.suggestionList}
              error={error}
              data-test-id="source-suggestions"
            >
              {suggestions.slice(0, 50).map((suggestion, index) => (
                <Suggestion
                  key={suggestion.value}
                  onClick={event => {
                    event.preventDefault();
                    this.handleClickSuggestionItem(suggestion);
                  }}
                  active={index === activeSuggestion}
                  tabIndex={-1}
                >
                  <TextOverflow>{suggestion.value}</TextOverflow>
                  {suggestion.description && (
                    <SuggestionDescription>
                      (<TextOverflow>{suggestion.description}</TextOverflow>)
                    </SuggestionDescription>
                  )}
                  {suggestion.examples && suggestion.examples.length > 0 && (
                    <SourceSuggestionExamples
                      examples={suggestion.examples}
                      sourceName={suggestion.value}
                    />
                  )}
                </Suggestion>
              ))}
            </Suggestions>
            <SuggestionsOverlay onClick={this.handleClickOutside} />
          </Fragment>
        )}
      </Wrapper>
    );
  }
}

export default SourceField;

const Wrapper = styled('div')<{hideCaret?: boolean}>`
  position: relative;
  width: 100%;
  ${p => p.hideCaret && `caret-color: transparent;`}
`;

const StyledTextField = styled(TextField)`
  z-index: 1002;
  :focus {
    outline: none;
  }
`;

const Suggestions = styled('ul')<{error?: string}>`
  position: absolute;
  width: ${p => (p.error ? 'calc(100% - 34px)' : '100%')};
  padding-left: 0;
  list-style: none;
  margin-bottom: 0;
  box-shadow: 0 2px 0 rgba(37, 11, 54, 0.04);
  border: 1px solid ${p => p.theme.border};
  border-radius: 0 0 ${space(0.5)} ${space(0.5)};
  background: ${p => p.theme.background};
  top: 63px;
  left: 0;
  z-index: 1002;
  overflow: hidden;
  max-height: 200px;
  overflow-y: auto;
`;

const Suggestion = styled('li')<{active: boolean}>`
  display: grid;
  grid-template-columns: auto 1fr max-content;
  gap: ${space(1)};
  border-bottom: 1px solid ${p => p.theme.border};
  padding: ${space(1)} ${space(2)};
  font-size: ${p => p.theme.fontSize.md};
  cursor: pointer;
  background: ${p => (p.active ? p.theme.backgroundSecondary : p.theme.background)};
  :hover {
    background: ${p =>
      p.active ? p.theme.backgroundSecondary : p.theme.backgroundSecondary};
  }
`;

const SuggestionDescription = styled('div')`
  display: flex;
  overflow: hidden;
  color: ${p => p.theme.subText};
  line-height: 1.2;
`;

const SuggestionsOverlay = styled('div')`
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 1001;
`;
