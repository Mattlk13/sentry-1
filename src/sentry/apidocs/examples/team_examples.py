from copy import deepcopy

from drf_spectacular.utils import OpenApiExample

from sentry.apidocs.examples.organization_member_examples import ORGANIZATION_MEMBER
from sentry.apidocs.examples.project_examples import PROJECT_SUMMARY

ORGANIZATION_MEMBER_ON_TEAM = deepcopy(ORGANIZATION_MEMBER)
ORGANIZATION_MEMBER_ON_TEAM["teamRole"] = "member"
ORGANIZATION_MEMBER_ON_TEAM["teamSlug"] = "powerful-abolitionist"

BASE_TEAM_1 = {
    "id": "4502349234123",
    "slug": "ancient-gabelers",
    "name": "Ancient Gabelers",
    "dateCreated": "2023-05-31T19:47:53.621181Z",
    "isMember": True,
    "teamRole": "contributor",
    "flags": {"idp:provisioned": False},
    "access": [
        "alerts:read",
        "event:write",
        "project:read",
        "team:read",
        "member:read",
        "project:releases",
        "event:read",
        "org:read",
    ],
    "hasAccess": True,
    "isPending": False,
    "memberCount": 3,
    "avatar": {"avatarType": "letter_avatar", "avatarUuid": None},
}

BASE_TEAM_2 = {
    "id": "4502349234125",
    "slug": "squeaky-minnows",
    "name": "Squeaky Minnows",
    "dateCreated": "2023-07-27T11:23:34.621181Z",
    "isMember": True,
    "teamRole": "contributor",
    "flags": {"idp:provisioned": False},
    "access": [
        "alerts:read",
        "event:write",
        "project:read",
        "team:read",
        "member:read",
        "project:releases",
        "event:read",
        "org:read",
    ],
    "hasAccess": True,
    "isPending": False,
    "memberCount": 5,
    "avatar": {"avatarType": "letter_avatar", "avatarUuid": None},
}


class TeamExamples:
    ADD_TO_TEAM = [
        OpenApiExample(
            "Join, request access to or add a member to a team",
            value=BASE_TEAM_1,
            status_codes=["201"],
            response_only=True,
        )
    ]

    CREATE_TEAM = [
        OpenApiExample(
            "Create a new team",
            value={
                "id": "5151492858",
                "slug": "ancient-gabelers",
                "name": "Ancient Gabelers",
                "dateCreated": "2021-06-12T23:38:54.168307Z",
                "isMember": True,
                "teamRole": "admin",
                "flags": {"idp:provisioned": False},
                "access": [
                    "project:write",
                    "member:read",
                    "event:write",
                    "team:admin",
                    "alerts:read",
                    "project:releases",
                    "alerts:write",
                    "org:read",
                    "team:read",
                    "project:admin",
                    "project:read",
                    "org:integrations",
                    "event:read",
                    "event:admin",
                    "team:write",
                ],
                "hasAccess": True,
                "isPending": False,
                "memberCount": 1,
                "avatar": {"avatarType": "letter_avatar", "avatarUuid": None},
            },
            status_codes=["201"],
            response_only=True,
        )
    ]

    DELETE_FROM_TEAM = [
        OpenApiExample(
            "Remove a member from a team",
            value={
                "id": "4502349234123",
                "slug": "ancient-gabelers",
                "name": "Ancient Gabelers",
                "dateCreated": "2023-05-31T19:47:53.621181Z",
                "isMember": False,
                "teamRole": None,
                "flags": {"idp:provisioned": False},
                "access": [
                    "alerts:read",
                    "event:write",
                    "project:read",
                    "team:read",
                    "member:read",
                    "project:releases",
                    "event:read",
                    "org:read",
                ],
                "hasAccess": True,
                "isPending": False,
                "memberCount": 3,
                "avatar": {"avatarType": "letter_avatar", "avatarUuid": None},
            },
            status_codes=["200"],
            response_only=True,
        )
    ]

    LIST_TEAM_MEMBERS = [
        OpenApiExample(
            "List Team Members",
            value=[ORGANIZATION_MEMBER_ON_TEAM],
            status_codes=["200"],
            response_only=True,
        )
    ]

    LIST_ORG_TEAMS = [
        OpenApiExample(
            "Get list of organization's teams",
            value=[
                {
                    "id": "48531",
                    "slug": "ancient-gabelers",
                    "name": "Ancient Gabelers",
                    "dateCreated": "2018-11-06T21:20:08.115Z",
                    "isMember": False,
                    "teamRole": None,
                    "flags": {"idp:provisioned": False},
                    "access": [
                        "member:read",
                        "alerts:read",
                        "org:read",
                        "event:read",
                        "project:read",
                        "project:releases",
                        "event:write",
                        "team:read",
                    ],
                    "hasAccess": True,
                    "isPending": False,
                    "memberCount": 2,
                    "avatar": {"avatarType": "letter_avatar", "avatarUuid": None},
                },
                {
                    "id": "100253",
                    "slug": "powerful-abolitionist",
                    "name": "Powerful Abolitionist",
                    "dateCreated": "2018-10-03T17:47:50.745447Z",
                    "isMember": False,
                    "teamRole": None,
                    "flags": {"idp:provisioned": False},
                    "access": [
                        "member:read",
                        "alerts:read",
                        "org:read",
                        "event:read",
                        "project:read",
                        "project:releases",
                        "event:write",
                        "team:read",
                    ],
                    "hasAccess": True,
                    "isPending": False,
                    "memberCount": 5,
                    "avatar": {"avatarType": "letter_avatar", "avatarUuid": None},
                    "projects": [
                        {
                            "id": "6403534",
                            "slug": "prime-mover",
                            "name": "Prime Mover",
                            "platform": None,
                            "dateCreated": "2019-04-06T00:02:40.468175Z",
                            "isBookmarked": False,
                            "isMember": False,
                            "features": [
                                "alert-filters",
                                "custom-inbound-filters",
                                "data-forwarding",
                                "discard-groups",
                                "minidump",
                                "rate-limits",
                                "servicehooks",
                                "similarity-indexing",
                                "similarity-indexing-v2",
                                "similarity-view",
                                "similarity-view-v2",
                                "releases",
                            ],
                            "firstEvent": "2019-04-06T02:00:21Z",
                            "firstTransactionEvent": True,
                            "access": [
                                "alerts:read",
                                "event:write",
                                "org:read",
                                "project:read",
                                "member:read",
                                "team:read",
                                "event:read",
                                "project:releases",
                            ],
                            "hasAccess": True,
                            "hasMinifiedStackTrace": False,
                            "hasMonitors": True,
                            "hasProfiles": False,
                            "hasReplays": False,
                            "hasFlags": False,
                            "hasFeedbacks": False,
                            "hasNewFeedbacks": False,
                            "hasSessions": True,
                            "hasInsightsHttp": True,
                            "hasInsightsDb": False,
                            "hasInsightsAssets": True,
                            "hasInsightsAppStart": False,
                            "hasInsightsScreenLoad": False,
                            "hasInsightsVitals": False,
                            "hasInsightsCaches": False,
                            "hasInsightsQueues": False,
                            "hasInsightsLlmMonitoring": False,
                            "hasInsightsAgentMonitoring": False,
                            "hasInsightsMCP": False,
                            "hasLogs": False,
                            "isInternal": False,
                            "isPublic": False,
                            "avatar": {"avatarType": "letter_avatar", "avatarUuid": None},
                            "color": "#6d3fbf",
                            "status": "active",
                        },
                        {
                            "id": "6403599",
                            "slug": "the-spoiled-yoghurt",
                            "name": "The Spoiled Yoghurt",
                            "platform": "",
                            "dateCreated": "2022-06-24T17:55:27.304367Z",
                            "isBookmarked": False,
                            "isMember": False,
                            "features": [
                                "alert-filters",
                                "custom-inbound-filters",
                                "data-forwarding",
                                "discard-groups",
                                "minidump",
                                "rate-limits",
                                "servicehooks",
                                "similarity-indexing",
                                "similarity-indexing-v2",
                                "similarity-view",
                                "similarity-view-v2",
                            ],
                            "firstEvent": "2022-07-13T18:17:56.197351Z",
                            "firstTransactionEvent": False,
                            "access": [
                                "alerts:read",
                                "event:write",
                                "org:read",
                                "project:read",
                                "member:read",
                                "team:read",
                                "event:read",
                                "project:releases",
                            ],
                            "hasAccess": True,
                            "hasMinifiedStackTrace": False,
                            "hasMonitors": True,
                            "hasProfiles": False,
                            "hasReplays": False,
                            "hasFlags": False,
                            "hasFeedbacks": False,
                            "hasNewFeedbacks": False,
                            "hasSessions": False,
                            "hasInsightsHttp": False,
                            "hasInsightsDb": True,
                            "hasInsightsAssets": True,
                            "hasInsightsAppStart": True,
                            "hasInsightsScreenLoad": True,
                            "hasInsightsVitals": False,
                            "hasInsightsCaches": False,
                            "hasInsightsQueues": False,
                            "hasInsightsLlmMonitoring": False,
                            "hasInsightsAgentMonitoring": False,
                            "hasInsightsMCP": False,
                            "hasLogs": False,
                            "isInternal": False,
                            "isPublic": False,
                            "avatar": {"avatarType": "letter_avatar", "avatarUuid": None},
                            "color": "#6e3fbf",
                            "status": "active",
                        },
                    ],
                },
            ],
            status_codes=["200"],
            response_only=True,
        )
    ]
    LIST_PROJECT_TEAMS = [
        OpenApiExample(
            "List a project's teams",
            value=[BASE_TEAM_1, BASE_TEAM_2],
            status_codes=["200"],
            response_only=True,
        )
    ]

    LIST_TEAM_PROJECTS = [
        OpenApiExample(
            "Get list of team's projects",
            value=[PROJECT_SUMMARY],
            status_codes=["200"],
            response_only=True,
        )
    ]

    RETRIEVE_TEAM_DETAILS = [
        OpenApiExample(
            "Retrieve a Team",
            value={
                "avatar": {"avatarType": "letter_avatar", "avatarUuid": None},
                "dateCreated": "2018-11-06T21:19:55.114Z",
                "hasAccess": True,
                "id": "2",
                "isMember": True,
                "isPending": False,
                "memberCount": 1,
                "name": "Powerful Abolitionist",
                "organization": {
                    "avatar": {"avatarType": "letter_avatar", "avatarUuid": None},
                    "dateCreated": "2018-11-06T21:19:55.101Z",
                    "id": "2",
                    "isEarlyAdopter": False,
                    "allowMemberInvite": True,
                    "allowMemberProjectCreation": True,
                    "allowSuperuserAccess": False,
                    "name": "The Interstellar Jurisdiction",
                    "require2FA": False,
                    "slug": "the-interstellar-jurisdiction",
                    "status": {"id": "active", "name": "active"},
                    "features": ["session-replay-videos"],
                    "hasAuthProvider": True,
                    "links": {
                        "organizationUrl": "https://philosophers.sentry.io",
                        "regionUrl": "https://us.sentry.io",
                    },
                },
                "slug": "powerful-abolitionist",
                "access": [
                    "event:read",
                    "event:write",
                    "team:read",
                    "org:read",
                    "project:read",
                    "member:read",
                    "project:releases",
                    "alerts:read",
                ],
                "flags": {"idp:provisioned": False},
                "teamRole": "contributor",
            },
            status_codes=["200"],
            response_only=True,
        )
    ]

    UPDATE_TEAM = [
        OpenApiExample(
            "Update a Team",
            value={
                "avatar": {"avatarType": "letter_avatar"},
                "dateCreated": "2018-11-06T21:20:08.115Z",
                "hasAccess": True,
                "id": "3",
                "isMember": False,
                "isPending": False,
                "memberCount": 1,
                "name": "The Inflated Philosophers",
                "slug": "the-inflated-philosophers",
                "access": [
                    "event:read",
                    "event:write",
                    "team:read",
                    "org:read",
                    "project:read",
                    "member:read",
                    "project:releases",
                    "alerts:read",
                ],
                "flags": {"idp:provisioned": False},
                "teamRole": "contributor",
            },
            status_codes=["200"],
            response_only=True,
        )
    ]

    UPDATE_TEAM_ROLE = [
        OpenApiExample(
            "Update a Team Role",
            value={
                "isActive": True,
                "teamRole": "admin",
            },
            status_codes=["200"],
            response_only=True,
        )
    ]
