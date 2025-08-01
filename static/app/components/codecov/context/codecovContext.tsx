import {createContext, useContext} from 'react';

export type CodecovContextData = {
  changeContextValue: (value: Partial<CodecovContextDataParams>) => void;
  codecovPeriod: string;
  branch?: string;
  integratedOrgId?: string;
  lastVisitedOrgId?: string;
  repository?: string;
};

export type CodecovContextDataParams = Omit<
  CodecovContextData,
  'changeContextValue' | 'lastVisitedOrgId'
>;

export const CodecovContext = createContext<CodecovContextData | undefined>(undefined);

export function useCodecovContext() {
  const context = useContext(CodecovContext);
  if (context === undefined)
    throw new Error('useCodecovContext was called outside of CodecovProvider');
  return context;
}
