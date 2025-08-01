import type {User} from 'sentry/types/user';

export function UserDetailsFixture(params: Partial<User> = {}): User {
  return {
    username: 'billyfirefoxusername@test.com',
    emails: [
      {is_verified: false, id: '20', email: 'billyfirefox@test.com2'},
      {is_verified: true, id: '8', email: 'billyfirefox2@test.com'},
      {is_verified: false, id: '7', email: 'billyfirefox@test.com'},
    ],
    isManaged: false,
    lastActive: '2018-01-25T21:00:19.946Z',
    identities: [],
    id: '4',
    isStaff: false,
    isActive: true,
    isSuperuser: false,
    isAuthenticated: true,
    ip_address: '',
    has2fa: false,
    name: 'Firefox Billy',
    avatarUrl:
      'https://secure.gravatar.com/avatar/5df53e28e63099658c1ba89b8e9a7cf4?s=32&d=mm',
    authenticators: [],
    dateJoined: '2018-01-11T00:30:41.366Z',
    options: {
      timezone: 'UTC',
      stacktraceOrder: 1,
      language: 'en',
      clock24Hours: false,
      defaultIssueEvent: 'recommended',
      avatarType: 'gravatar',
      theme: 'light',
      prefersIssueDetailsStreamlinedUI: false,
      prefersNextjsInsightsOverview: false,
      prefersAgentsInsightsModule: false,
      prefersStackedNavigation: false,
      prefersChonkUI: false,
    },
    avatar: {avatarUuid: null, avatarType: 'letter_avatar'},
    lastLogin: '2018-01-25T19:57:46.973Z',
    permissions: new Set(),
    email: 'billyfirefox@test.com',
    canReset2fa: false,
    flags: {newsletter_consent_prompt: false},
    hasPasswordAuth: false,
    ...params,
  };
}
