from unittest import TestCase

from sentry.integrations.source_code_management.language_parsers import (
    CSharpParser,
    GoParser,
    JavascriptParser,
    PHPParser,
    PythonParser,
    RubyParser,
)


class PythonParserTestCase(TestCase):
    def test_python(self) -> None:
        # from https://github.com/getsentry/sentry/pull/61981
        patch = """@@ -36,6 +36,7 @@\n from sentry.templatetags.sentry_helpers import small_count\n from sentry.types.referrer_ids import GITHUB_OPEN_PR_BOT_REFERRER\n from sentry.utils import metrics\n+from sentry.utils.json import JSONData\n from sentry.utils.snuba import raw_snql_query\n \n logger = logging.getLogger(__name__)\n@@ -134,10 +135,10 @@ def get_issue_table_contents(issue_list: List[Dict[str, int]]) -> List[PullReque\n # TODO(cathy): Change the client typing to allow for multiple SCM Integrations\n def safe_for_comment(\n     gh_client: GitHubApiClient, repository: Repository, pull_request: PullRequest\n-) -> bool:\n+) -> Tuple[bool, JSONData]:\n     logger.info("github.open_pr_comment.check_safe_for_comment")\n     try:\n-        pullrequest_resp = gh_client.get_pullrequest(\n+        pr_files = gh_client.get_pullrequest_files(\n             repo=repository.name, pull_number=pull_request.key\n         )\n     except ApiError as e:\n@@ -158,34 +159,47 @@ def safe_for_comment(\n                 tags={"type": GithubAPIErrorType.UNKNOWN.value, "code": e.code},\n             )\n             logger.exception("github.open_pr_comment.unknown_api_error", extra={"error": str(e)})\n-        return False\n+        return False, []\n \n     safe_to_comment = True\n-    if pullrequest_resp["state"] != "open":\n-        metrics.incr(\n-            OPEN_PR_METRICS_BASE.format(key="rejected_comment"), tags={"reason": "incorrect_state"}\n-        )\n-        safe_to_comment = False\n-    if pullrequest_resp["changed_files"] > OPEN_PR_MAX_FILES_CHANGED:\n+\n+    changed_file_count = 0\n+    changed_lines_count = 0\n+\n+    for file in pr_files:\n+        filename = file["filename"]\n+        # don't count the file if it was added or is not a Python file\n+        if file["status"] == "added" or not filename.endswith(".py"):\n+            continue\n+\n+        changed_file_count += 1\n+        changed_lines_count += file["changes"]\n+\n+    if changed_file_count > OPEN_PR_MAX_FILES_CHANGED:\n         metrics.incr(\n             OPEN_PR_METRICS_BASE.format(key="rejected_comment"), tags={"reason": "too_many_files"}\n         )\n         safe_to_comment = False\n-    if pullrequest_resp["additions"] + pullrequest_resp["deletions"] > OPEN_PR_MAX_LINES_CHANGED:\n+    if changed_lines_count > OPEN_PR_MAX_LINES_CHANGED:\n         metrics.incr(\n             OPEN_PR_METRICS_BASE.format(key="rejected_comment"), tags={"reason": "too_many_lines"}\n         )\n         safe_to_comment = False\n-    return safe_to_comment\n \n+    if not safe_to_comment:\n+        pr_files = []\n+\n+    return safe_to_comment, pr_files\n \n-def get_pr_filenames(\n-    gh_client: GitHubApiClient, repository: Repository, pull_request: PullRequest\n-) -> List[str]:\n-    pr_files = gh_client.get_pullrequest_files(repo=repository.name, pull_number=pull_request.key)\n \n+def get_pr_filenames(pr_files: JSONData) -> List[str]:\n     # new files will not have sentry issues associated with them\n-    pr_filenames: List[str] = [file["filename"] for file in pr_files if file["status"] != "added"]\n+    # only fetch Python files\n+    pr_filenames: List[str] = [\n+        file["filename"]\n+        for file in pr_files\n+        if file["status"] != "added" and file["filename"].endswith(".py")\n+    ]\n \n     logger.info("github.open_pr_comment.pr_filenames", extra={"count": len(pr_filenames)})\n     return pr_filenames\n@@ -316,15 +330,22 @@ def open_pr_comment_workflow(pr_id: int) -> None:\n     client = installation.get_client()\n \n     # CREATING THE COMMENT\n-    if not safe_for_comment(gh_client=client, repository=repo, pull_request=pull_request):\n+    logger.info("github.open_pr_comment.check_safe_for_comment")\n+\n+    # fetch the files in the PR and determine if it is safe to comment\n+    safe_to_comment, pr_files = safe_for_comment(\n+        gh_client=client, repository=repo, pull_request=pull_request\n+    )\n+\n+    if not safe_to_comment:\n         logger.info("github.open_pr_comment.not_safe_for_comment")\n         metrics.incr(\n             OPEN_PR_METRICS_BASE.format(key="error"),\n             tags={"type": "unsafe_for_comment"},\n         )\n         return\n \n-    pr_filenames = get_pr_filenames(gh_client=client, repository=repo, pull_request=pull_request)\n+    pr_filenames = get_pr_filenames(pr_files)\n \n     issue_table_contents = {}\n     top_issues_per_file = []"""
        assert PythonParser.extract_functions_from_patch(patch) == {
            "get_issue_table_contents",
            "safe_for_comment",
            "open_pr_comment_workflow",
        }

    def test_python_in_class(self) -> None:
        # from https://github.com/getsentry/sentry/pull/59152
        patch = '@@ -274,6 +274,14 @@ def patch(self, request: Request, organization, member):\n \n         result = serializer.validated_data\n \n+        if getattr(member.flags, "partnership:restricted"):\n+            return Response(\n+                {\n+                    "detail": "This member is managed by an active partnership and cannot be modified until the end of the partnership."\n+                },\n+                status=403,\n+            )\n+\n         for operation in result["operations"]:\n             # we only support setting active to False which deletes the orgmember\n             if self._should_delete_member(operation):\n@@ -310,6 +318,14 @@ def delete(self, request: Request, organization, member) -> Response:\n         """\n         Delete an organization member with a SCIM User DELETE Request.\n         """\n+        if getattr(member.flags, "partnership:restricted"):\n+            return Response(\n+                {\n+                    "detail": "This member is managed by an active partnership and cannot be modified until the end of the partnership."\n+                },\n+                status=403,\n+            )\n+\n         self._delete_member(request, organization, member)\n         metrics.incr("sentry.scim.member.delete", tags={"organization": organization})\n         return Response(status=204)\n@@ -348,6 +364,14 @@ def put(self, request: Request, organization, member):\n             )\n             return Response(context, status=200)\n \n+        if getattr(member.flags, "partnership:restricted"):\n+            return Response(\n+                {\n+                    "detail": "This member is managed by an active partnership and cannot be modified until the end of the partnership."\n+                },\n+                status=403,\n+            )\n+\n         if request.data.get("sentryOrgRole"):\n             # Don\'t update if the org role is the same\n             if ('
        assert PythonParser.extract_functions_from_patch(patch) == {
            "patch",
            "delete",
            "put",
        }


class JavascriptParserTestCase(TestCase):
    def test_javascript_simple(self) -> None:
        patch = """\
@@44,38@@ function hello(argument1, argument2)

@@44,38@@ export default function world({argument}) {

@@44,38@@ async function there()

@@44,38@@ async function wow(

@@44,38@@ export const blue = () => {

@@44,38@@ export const green = (argument) =>

@@44,38@@ export const ocean = async (argument) => {

@@44,38@@ const planet = async function(argument) {

@@44,38@@ const constructor = new Function(

@@44,38@@ const noMatch = {"""

        assert JavascriptParser.extract_functions_from_patch(patch) == {
            "hello",
            "world",
            "ocean",
            "blue",
            "planet",
            "constructor",
            "there",
            "green",
            "wow",
        }

        # reference: https://github.com/jquery/esprima/tree/main/test/fixtures/declaration/function
        patch = """\
@@44,38@@ function noArguments1() { }

@@44,38@@ function noArguments2() {

@@44,38@@ function test1(t, t) { }

@@44,38@@ function test2(t, t) { }

@@44,38@@ (function test3(t, t) { })

@@44,38@@ function hasInnerFunction1() { function inner() { "use strict" } }

@@44,38@@ function hasInnerFunction2(a) { sayHi();

@@44,38@@ function hasInnerFunction3(a, b) { sayHi(); }

@@44,38@@ var varFunction1 = function() { sayHi() };

@@44,38@@ var varFunction2 = function() {

@@44,38@@ var varFunction3 = function eval() { };

@@44,38@@ var varFunction4 = function arguments(

@@44,38@@ var varFunction5 = function hi() { sayHi() };

@@44,38@@ function protoFunction(__proto__) { }

@@44,38@@ function test() { "use strict" + 42; }

@@44,38@@ function a(x, x) {'use strict';}

@@44,38@@ function hello() { sayHi(); }

@@44,38@@ function lol() { }
"""

        assert JavascriptParser.extract_functions_from_patch(patch) == {
            "noArguments1",
            "noArguments2",
            "test1",
            "test2",
            "test3",
            "hasInnerFunction1",
            "hasInnerFunction2",
            "hasInnerFunction3",
            "varFunction1",
            "varFunction2",
            "varFunction3",
            "varFunction4",
            "varFunction5",
            "protoFunction",
            "test",
            "a",
            "hello",
            "lol",
        }

    # reference https://github.com/jquery/esprima/tree/main/test/fixtures/ES6/arrow-function
    # tests arrow functions on the same line as the hunk header
    patch = """\
@@44,38@@ export const arrow1 = (...a) => {

@@44,38@@ var arrow2 = (a, ...b) => 0;

@@44,38@@ var arrow3 = ((a)) => 0

@@44,38@@ const arrow4 = (sun) => earth

@@44,38@@ const arrow5 = foo((x, y) => {})

@@44,38@@ const arrow6 = foo(() => {})

@@44,38@@ const arrow7 = (x) => ((y, z) => (x, y, z))

@@44,38@@ const arrow8 = x => y => 42

@@44,38@@ const arrow9 = (x) => y => 42

@@44,38@@ const arrow10 = (x => x)

@@44,38@@ const arrow11 = (eval, a = 10) => 42

@@44,38@@ const arrow12 = (eval = 10) => 42

@@44,38@@ const arrow13 = (eval, a) => 42

@@44,38@@ const arrow14 = (a) => 00

@@44,38@@ const arrow15 = arguments => 42

@@44,38@@ const arrow16 = (x=1) => x * x

@@44,38@@ const arrow17 = (a, b) => { 42; }

@@44,38@@ const arrow18 = e => { label: 42 }

@@44,38@@ const arrow19 = e => ({ property: 42 })

@@44,38@@ const arrow20 = e => { 42; }

@@44,38@@ const arrow21 = (a, b) => "test"

@@44,38@@ const arrow22 = (e) => "test"

@@44,38@@ const arrow23 = e => e + 1

@@44,38@@ const arrow24 = e => "test"

@@44,38@@ const arrow25 = () => "test"

@@44,38@@ var arrow26 = (...a) => 0

@@44,38@@ var arrow27 = (...a, ...b) => 0

@@44,38@@ var arrow28 = (a,b,...c) => 0;

@@44,38@@ var arrow29 = (a ...b) => 0
"""

    functions = JavascriptParser.extract_functions_from_patch(patch)

    for i in range(1, 30):
        assert "arrow" + str(i) in functions

    def test_typescript_simple(self) -> None:
        patch = """\
@@44,38@@ function hello():

@@44,38@@ export default function world({argument: int, other: string}) {

@@44,38@@ async function there()

@@44,38@@ async function wow(

@@44,38@@ export const blue = () => {

@@44,38@@ export const green = (argument: string) =>

@@44,38@@ export const ocean = useMemo(() => {

@@44,38@@ const planet = async function({argument, ...props}) {

@@44,38@@ const constructor = new Function(

@@44,38@@ const noMatch = {"""

        assert JavascriptParser.extract_functions_from_patch(patch) == {
            "hello",
            "world",
            "ocean",
            "blue",
            "planet",
            "constructor",
            "there",
            "green",
            "wow",
        }

        # reference: https://github.com/jquery/esprima/tree/main/test/fixtures/declaration/function
        patch = """\
@@44,38@@ function noArguments1() { }

@@44,38@@ function noArguments2() {

@@44,38@@ function test1(t: string, t: int) { }

@@44,38@@ function test2(t: int[], t: string[]) { }

@@44,38@@ (function test3(t, t) { })

@@44,38@@ function hasInnerFunction1() { function inner() { "use strict" } }

@@44,38@@ function hasInnerFunction2(a: string) { sayHi();

@@44,38@@ function hasInnerFunction3(a: string, b: string) { sayHi(); }

@@44,38@@ var varFunction1 = function() { sayHi() };

@@44,38@@ var varFunction2 = function() {

@@44,38@@ var varFunction3 = function eval() { };

@@44,38@@ var varFunction4 = function arguments(

@@44,38@@ var varFunction5 = function hi() { sayHi() };

@@44,38@@ function protoFunction(__proto__) { }

@@44,38@@ function test() { "use strict" + 42; }

@@44,38@@ function a(x: string, x: int) {'use strict';}

@@44,38@@ function hello() { sayHi(); }

@@44,38@@ function lol() { }
"""

        assert JavascriptParser.extract_functions_from_patch(patch) == {
            "noArguments1",
            "noArguments2",
            "test1",
            "test2",
            "test3",
            "hasInnerFunction1",
            "hasInnerFunction2",
            "hasInnerFunction3",
            "varFunction1",
            "varFunction2",
            "varFunction3",
            "varFunction4",
            "varFunction5",
            "protoFunction",
            "test",
            "a",
            "hello",
            "lol",
        }

    # reference https://github.com/jquery/esprima/tree/main/test/fixtures/ES6/arrow-function
    # tests arrow functions on the same line as the hunk header
    patch = """\
@@44,38@@ export const arrow1 = (...a) => {

@@44,38@@ var arrow2 = (a, ...b) => 0;

@@44,38@@ var arrow3 = ((a)) => 0

@@44,38@@ const arrow4 = (sun: planet) => earth

@@44,38@@ const arrow5 = foo((x: a, y: b) => {})

@@44,38@@ const arrow6 = foo(() => {})

@@44,38@@ const arrow7 = (x: string) => ((y, z) => (x, y, z))

@@44,38@@ const arrow8 = x => y => 42

@@44,38@@ const arrow9 = (x: () => {}) => y => 42

@@44,38@@ const arrow10 = (x => x)

@@44,38@@ const arrow11 = (eval: string, a: int = 10) => 42

@@44,38@@ const arrow12 = (eval:int = 10) => 42

@@44,38@@ const arrow13 = (eval: int, a: () => void) => 42

@@44,38@@ const arrow14 = (a: int) => 00

@@44,38@@ const arrow15 = arguments => 42

@@44,38@@ const arrow16 = (x: int=1) => x * x

@@44,38@@ const arrow17 = (a: int, b: int) => { 42; }

@@44,38@@ const arrow18 = e => { label: 42 }

@@44,38@@ const arrow19 = e => ({ property: 42 })

@@44,38@@ const arrow20 = e => { 42; }

@@44,38@@ const arrow21 = (a: () => void, b: int) => "test"

@@44,38@@ const arrow22 = (e: string) => "test"

@@44,38@@ const arrow23 = e => e + 1

@@44,38@@ const arrow24 = e => "test"

@@44,38@@ const arrow25 = () => "test"

@@44,38@@ var arrow26 = (...a) => 0

@@44,38@@ var arrow27 = (...a, ...b) => 0

@@44,38@@ var arrow28 = (a: string,b: int,...c) => 0;

@@44,38@@ var arrow29 = (a ...b) => 0
"""

    functions = JavascriptParser.extract_functions_from_patch(patch)

    for i in range(1, 30):
        assert "arrow" + str(i) in functions

    def test_typescript_example(self) -> None:
        # from https://github.com/getsentry/sentry/pull/61329
        patch = """\
@@ -40,6 +40,7 @@ import {space} from 'sentry/styles/space';
 import {Organization} from 'sentry/types';
 import {isDemoWalkthrough} from 'sentry/utils/demoMode';
 import {getDiscoverLandingUrl} from 'sentry/utils/discover/urls';
+import {isActiveSuperuser} from 'sentry/utils/isActiveSuperuser';
 import theme from 'sentry/utils/theme';
 import {useLocation} from 'sentry/utils/useLocation';
 import useMedia from 'sentry/utils/useMedia';
@@ -115,6 +116,7 @@ function Sidebar({organization}: Props) {

   const collapsed = !!preferences.collapsed;
   const horizontal = useMedia(`(max-width: ${theme.breakpoints.md})`);
+  const hasSuperuserSession = isActiveSuperuser(organization);

   useOpenOnboardingSidebar();

@@ -497,7 +499,11 @@ function Sidebar({organization}: Props) {
   );

   return (
-    <SidebarWrapper aria-label={t('Primary Navigation')} collapsed={collapsed}>
+    <SidebarWrapper
+      aria-label={t('Primary Navigation')}
+      collapsed={collapsed}
+      isSuperuser={hasSuperuserSession}
+    >
       <SidebarSectionGroupPrimary>
         <SidebarSection>
           <SidebarDropdown
@@ -634,9 +640,10 @@ const responsiveFlex = css`
   }
 `;

-export const SidebarWrapper = styled('nav')<{collapsed: boolean}>`
-  background: ${p => p.theme.sidebarGradient};
-  color: ${p => p.theme.sidebar.color};
+export const SidebarWrapper = styled('nav')<{collapsed: boolean; isSuperuser?: boolean}>`
+  background: ${p =>
+    p.isSuperuser ? p.theme.superuserSidebar : p.theme.sidebarGradient};
+  color: ${p => (p.isSuperuser ? 'white' : p.theme.sidebar.color)};
   line-height: 1;
   padding: 12px 0 2px; /* Allows for 32px avatars  */
   width: ${p => p.theme.sidebar[p.collapsed ? 'collapsedWidth' : 'expandedWidth']};"""

        assert JavascriptParser.extract_functions_from_patch(patch) == {"Sidebar"}

        # from https://github.com/getsentry/sentry/pull/55411
        patch = """\
@@ -1,9 +1,11 @@
 import {useCallback, useEffect, useState} from 'react';
 import styled from '@emotion/styled';
+import * as qs from 'query-string';

 import {openInviteMissingMembersModal} from 'sentry/actionCreators/modal';
 import {promptsCheck, promptsUpdate} from 'sentry/actionCreators/prompts';
 import {Button} from 'sentry/components/button';
+import {ButtonBar} from 'sentry/components/buttonBar';
 import Card from 'sentry/components/card';
 import Carousel from 'sentry/components/carousel';
 import {openConfirmModal} from 'sentry/components/confirm';
@@ -16,6 +18,7 @@ import {space} from 'sentry/styles/space';
 import {MissingMember, Organization, OrgRole} from 'sentry/types';
 import {promptIsDismissed} from 'sentry/utils/promptIsDismissed';
 import useApi from 'sentry/utils/useApi';
+import {useLocation} from 'sentry/utils/useLocation';
 import withOrganization from 'sentry/utils/withOrganization';

 type Props = {
@@ -46,6 +49,7 @@ export function InviteBanner({
   const api = useApi();
   const integrationName = missingMembers?.integration;
   const promptsFeature = `${integrationName}_missing_members`;
+  const location = useLocation();

   const snoozePrompt = useCallback(async () => {
     setShowBanner(false);
@@ -56,6 +60,15 @@ export function InviteBanner({
     });
   }, [api, organization, promptsFeature]);

+  const openInviteModal = useCallback(() => {
+    openInviteMissingMembersModal({
+      allowedRoles,
+      missingMembers,
+      organization,
+      onClose: onModalClose,
+    });
+  }, [allowedRoles, missingMembers, organization, onModalClose]);
+
   useEffect(() => {
     if (hideBanner) {
       return;
@@ -68,6 +81,14 @@ export function InviteBanner({
     });
   }, [api, organization, promptsFeature, hideBanner]);

+  useEffect(() => {
+    const {inviteMissingMembers} = qs.parse(location.search);
+
+    if (!hideBanner && inviteMissingMembers) {
+      openInviteModal();
+    }
+  }, [openInviteModal, location, hideBanner]);
+
   if (hideBanner || !showBanner) {
     return null;
   }
@@ -134,9 +155,7 @@ export function InviteBanner({
     <SeeMoreCard
       key="see-more"
       missingMembers={missingMembers}
-      allowedRoles={allowedRoles}
-      onModalClose={onModalClose}
-      organization={organization}
+      openInviteModal={openInviteModal}
     />
   );

@@ -157,19 +176,8 @@ export function InviteBanner({
             />
           </Subtitle>
         </CardTitleContent>
-        <ButtonContainer>
-          <Button
-            priority="primary"
-            size="xs"
-            onClick={() =>
-              openInviteMissingMembersModal({
-                allowedRoles,
-                missingMembers,
-                onClose: onModalClose,
-                organization,
-              })
-            }
-          >
+        <ButtonBar gap={1}>
+          <Button priority="primary" size="xs" onClick={openInviteModal}>
             {t('View All')}
           </Button>
           <DropdownMenu
@@ -181,7 +189,7 @@ export function InviteBanner({
               'aria-label': t('Actions'),
             }}
           />
-        </ButtonContainer>
+        </ButtonBar>
       </CardTitleContainer>
       <Carousel>{cards}</Carousel>
     </StyledCard>
@@ -191,18 +199,11 @@ export function InviteBanner({
 export default withOrganization(InviteBanner);

 type SeeMoreCardProps = {
-  allowedRoles: OrgRole[];
   missingMembers: {integration: string; users: MissingMember[]};
-  onModalClose: () => void;
-  organization: Organization;
+  openInviteModal: () => void;
 };

-function SeeMoreCard({
-  missingMembers,
-  allowedRoles,
-  onModalClose,
-  organization,
-}: SeeMoreCardProps) {
+function SeeMoreCard({missingMembers, openInviteModal}: SeeMoreCardProps) {
   const {users} = missingMembers;

   return (
@@ -221,18 +222,7 @@ function SeeMoreCard({
           })}
         </Subtitle>
       </MemberCardContent>
-      <Button
-        size="sm"
-        priority="primary"
-        onClick={() =>
-          openInviteMissingMembersModal({
-            allowedRoles,
-            missingMembers,
-            organization,
-            onClose: onModalClose,
-          })
-        }
-      >
+      <Button size="sm" priority="primary" onClick={openInviteModal}>
         {t('View All')}
       </Button>
     </MemberCard>
@@ -269,17 +259,7 @@ export const Subtitle = styled('div')`
   font-size: ${p => p.theme.fontSize.sm};
   font-weight: 400;
   color: ${p => p.theme.gray300};
-  & > *:first-child {
-    margin-left: ${space(0.5)};
-    display: flex;
-    align-items: center;
-  }
-`;
-
-const ButtonContainer = styled('div')`
-  display: grid;
-  grid-auto-flow: column;
-  grid-column-gap: ${space(1)};
+  gap: ${space(0.5)};
 `;

 const MemberCard = styled(Card)`
@@ -305,9 +285,7 @@ const MemberCardContentRow = styled('div')`
   align-items: center;
   margin-bottom: ${space(0.25)};
   font-size: ${p => p.theme.fontSize.sm};
-  & > *:first-child {
-    margin-right: ${space(0.75)};
-  }
+  gap: ${space(0.75)};
 `;

 export const StyledExternalLink = styled(ExternalLink)`"""

        assert JavascriptParser.extract_functions_from_patch(patch) == {
            "InviteBanner",
            "SeeMoreCard",
        }

    def test_javascript_functions_after_const(self) -> None:

        patch = """
          "@@ -305,9 +285,7 @@ export const Redacted Redacted\n   // Redacted.\n   // Redacted \n   const redacted = redacted;\n+  const redacted = redacted();\n+  // const redacted = true;\n+  const redacted = redacted()\n+    redacted; // Redacted\nconst \n@@ -165,24 +171,40 @@ export const RedactedRedactedRedactedRedactedRedacted

          // Redacted
@@44,38@@ var arrow2 = (a, ...b) => 0;


            "@@ -305,9 +285,7 @@ export const Redacted Redacted\n   // Redacted.\n   // Redacted \n   const redacted = redacted;\n+  const redacted = redacted();\n+  // const redacted = true;\n+  const redacted = redacted()\n+    redacted; // Redacted\nconst \n@@ -165,24 +171,40@@ export const RedactedRedactedRedactedRedactedRedacted

            // Redacted
@@44,38@@ const planet = async function(argument) {
            "@@ -305,9 +285,7 @@ export const Redacted Redacted\n   // Redacted.\n   // Redacted \n   const redacted = redacted;\n+  const redacted = redacted();\n+  // const redacted = true;\n+  const redacted = redacted()\n+    redacted; // Redacted\nconst \n@@ -165,24 +171,40@@ export const RedactedRedactedRedactedRedactedRedacted

            // Redacted
@@44,38@@ const constructor = new Function(
            "@@ -305,9 +285,7 @@ export const Redacted Redacted\n   // Redacted.\n   // Redacted \n   const redacted = redacted;\n+  const redacted = redacted();\n+  // const redacted = true;\n+  const redacted = redacted()\n+    redacted; // Redacted\nconst \n@@ -165,24 +171,40@@ export const RedactedRedactedRedactedRedactedRedacted

            // Redacted
@@44,38@@ function hello(argument1, argument2)

"""
        assert JavascriptParser.extract_functions_from_patch(patch) == {
            "arrow2",
            "planet",
            "constructor",
            "hello",
        }


class PHPParserTestCase(TestCase):
    def test_php_simple(self) -> None:
        patch = """
@@ -51,7 +51,7 @@ $arrowFunc = fn($parameter) => $parameter + 1;

@@ -45,7 +45,7 @@ $anonFunc = function ($parameter) {

@@ -45,7 +45,7 @@ $var = function($parameter) {

@@ -45,7 +45,7 @@ public function title()

@@ -45,7 +45,7 @@ public function download(string $filename = 'document.pdf'): Response

@@ -45,7 +45,7 @@ protected function isLumen(): bool

@@ -45,7 +45,7 @@ export function escapeHtml(string) {

@@ -45,7 +45,7 @@ public function tests()

@@ -45,7 +45,7 @@ public static function toEnvelopeItem(Event $event): string

@@ -45,7 +45,7 @@ $greet = function($name) {
    printf("Hello %s\r\n", $name);
};

@@ -45,7 +45,7 @@ $outer = fn($x) => fn($y) => $x * $y + $z;

@@ -45,7 +45,7@@ $hi = no_match($name);

@@ -1,3 +1,3 @@ public static function subtract(x, y)

@@ -5,5 +5,5 @@ $multiply=function(x, y) { return x * y; }

@@ -5,5 +5,5 @@ $divide= function(x, y) { return x / y; }

@@ -25,14 +25,14 @@ $hello = function(name) { return "Hello, " + name; }

@@ -35,18 +35,18 @@ $reduce = fn($values) => array_reduce($values, function($carry, $item) { return $carry + $item; });

@@ -45,22 +45,22 @@ public static function transformData(data)

"""
        assert PHPParser.extract_functions_from_patch(patch) == {
            "arrowFunc",
            "anonFunc",
            "var",
            "title",
            "download",
            "isLumen",
            "escapeHtml",
            "tests",
            "toEnvelopeItem",
            "greet",
            "outer",
            "subtract",
            "multiply",
            "divide",
            "hello",
            "reduce",
            "transformData",
        }

    def test_php_example(self) -> None:
        # reference: https://github.com/getsentry/gib-potato/pull/45
        patch = """
@@ -152,10 +152,6 @@ public function up(): void
                ]
            )
            ->update();

        $this->table('products')->drop()->save();

        $this->table('purchases')->drop()->save();
    }

    /**
@@ -184,93 +180,6 @@ public function down(): void
            ->dropForeignKey(
                'user_id'
            )->save();
        $this->table('products')
            ->addColumn('name', 'string', [
                'default' => null,
                'limit' => 255,
                'null' => false,
            ])
            ->addColumn('description', 'text', [
                'default' => null,
                """

        assert PHPParser.extract_functions_from_patch(patch) == {
            "up",
            "down",
        }

        patch = """
@@ -184,93 +180,6 @@ function one() {

@@ -184,93 +180,6 @@ function two () {

@@ -184,93 +180,6 @@ $three = function() {

@@ -184,93 +180,6 @@ $four = static function() {

@@ -184,93 +180,6 @@ $five = fn() => 1 + 1;

@@ -184,93 +180,6 @@ $six = static fn() => 1 + 1;

@@ -184,93 +180,6 @@ function seven() {

@@ -184,93 +180,6 @@ static function eight() {

@@ -184,93 +180,6 @@ public function nine() {

@@ -184,93 +180,6 @@ public static function ten() {
"""

        assert PHPParser.extract_functions_from_patch(patch) == {
            "one",
            "two",
            "three",
            "four",
            "five",
            "six",
            "seven",
            "eight",
            "nine",
            "ten",
        }


class RubyParserTestCase(TestCase):
    def test_ruby_simple(self) -> None:
        patch = """
@@ -152,10 +152,6 @@ def one ()

@@ -152,10 +152,6 @@ def two()

@@ -152,10 +152,6 @@ def self.three()

@@ -152,10 +152,6 @@ def obj.four ()

@@ -152,10 +152,6 @@ define_method :five do

@@ -152,10 +152,6 @@ six = -> { puts "This is a lambda." }

@@ -152,10 +152,6 @@ seven = lambda { puts "This is a lambda."}

"""

        assert RubyParser.extract_functions_from_patch(patch) == {
            "one",
            "two",
            "three",
            "four",
            "five",
            "six",
            "seven",
        }

    def test_ruby_example(self) -> None:
        patch = """
@@ -73,9 +73,7 @@ def for(name)

@@ -73,9 +73,7 @@ def for_2 (name)

@@ -20,6 +20,7 @@ def initialize(detach: true)

@@ -27,7 +27,8 @@ def token

@@ -46,7 +46,7 @@ def on_block(node) # rubocop:disable InternalAffairs/NumblockHandler

@@ -47,7 +47,7 @@ def message_franking

@@ -821,7 +821,7 @@ def to_liquid

@@ -203,4 +207,23 @@ def render_content_with_collection(content, collection_label)

@@ -203,4 +207,23 @@ def render_content_with_collection_2 (content, collection_label)

@@ -36,10 +36,13 @@ def require_gems

"""

        assert RubyParser.extract_functions_from_patch(patch) == {
            "for",
            "for_2",
            "initialize",
            "token",
            "on_block",
            "message_franking",
            "to_liquid",
            "render_content_with_collection",
            "render_content_with_collection_2",
            "require_gems",
        }


class CSharpParserTestCase(TestCase):
    def test_csharp_simple(self) -> None:
        patch = """
@@ -152,10 +152,6 @@ public void MethodOne()

@@ -152,10 +152,6 @@ private static int MethodTwo(int x)

@@ -152,10 +152,6 @@ protected virtual string MethodThree()

@@ -152,10 +152,6 @@ internal async Task<string> MethodFour()

@@ -152,10 +152,6 @@ public async Task MethodFive()

@@ -152,10 +152,6 @@ static void MethodSix()

@@ -152,10 +152,6 @@ public override bool MethodSeven()

@@ -152,10 +152,6 @@ public abstract void MethodEight()

@@ -152,10 +152,6 @@ public ClassName()

@@ -152,10 +152,6 @@ static ClassName()

@@ -152,10 +152,6 @@ ~ClassName()

@@ -152,10 +152,6 @@ get { return _value; }

@@ -152,10 +152,6 @@ set { _value = value; }

@@ -152,10 +152,6 @@ public int Add(int x, int y) => x + y;

@@ -152,10 +152,6 @@ void LocalFunction()

@@ -152,10 +152,6 @@ async Task<string> AsyncLocalFunction()

"""

        assert CSharpParser.extract_functions_from_patch(patch) == {
            "MethodOne",
            "MethodTwo",
            "MethodThree",
            "MethodFour",
            "MethodFive",
            "MethodSix",
            "MethodSeven",
            "MethodEight",
            "ClassName",
            "get",
            "set",
            "Add",
            "LocalFunction",
            "AsyncLocalFunction",
        }

    def test_csharp_operators(self) -> None:
        patch = """
@@ -152,10 +152,6 @@ public static ClassName operator+(ClassName a, ClassName b)

@@ -152,10 +152,6 @@ public static bool operator==(ClassName a, ClassName b)

@@ -152,10 +152,6 @@ public static implicit operator string(ClassName obj)

@@ -152,10 +152,6 @@ public static explicit operator int(ClassName obj)

@@ -152,10 +152,6 @@ public static ClassName operator++(ClassName obj)

@@ -152,10 +152,6 @@ public static bool operator<(ClassName a, ClassName b)

@@ -152,10 +152,6 @@ public static bool operator>(ClassName a, ClassName b)

"""

        assert CSharpParser.extract_functions_from_patch(patch) == {
            "+",
            "==",
            "implicit",
            "explicit",
            "++",
            "<",
            ">",
        }

    def test_csharp_generics_and_complex_types(self) -> None:
        patch = """
@@ -152,10 +152,6 @@ public List<T> GetItems<T>()

@@ -152,10 +152,6 @@ public Dictionary<string, int> GetDictionary()

@@ -152,10 +152,6 @@ public async Task<List<string>> GetStringsAsync()

@@ -152,10 +152,6 @@ public T[] GetArray<T>(int size)

@@ -152,10 +152,6 @@ public void ProcessItems(List<Dictionary<string, object>> items)

@@ -152,10 +152,6 @@ public Func<int, bool> GetPredicate()

@@ -152,10 +152,6 @@ public Action<string> GetAction()

@@ -152,10 +152,6 @@ public int? GetNullableInt()

"""

        assert CSharpParser.extract_functions_from_patch(patch) == {
            "GetItems",
            "GetDictionary",
            "GetStringsAsync",
            "GetArray",
            "ProcessItems",
            "GetPredicate",
            "GetAction",
            "GetNullableInt",
        }

    def test_csharp_expression_bodied_members(self) -> None:
        patch = """
@@ -152,10 +152,6 @@ public int Add(int x, int y) => x + y;

@@ -152,10 +152,6 @@ public string FullName => $"{FirstName} {LastName}";

@@ -152,10 +152,6 @@ public bool IsValid => !string.IsNullOrEmpty(Name);

@@ -152,10 +152,6 @@ private static string FormatValue(object value) => value?.ToString() ?? "null";

@@ -152,10 +152,6 @@ public async Task<string> GetDataAsync() => await LoadDataAsync();

@@ -152,10 +152,6 @@ public override string ToString() => $"Object: {Name}";

"""

        assert CSharpParser.extract_functions_from_patch(patch) == {
            "Add",
            "FullName",
            "IsValid",
            "FormatValue",
            "GetDataAsync",
            "ToString",
        }

    def test_csharp_real_world_example(self) -> None:
        # Based on a typical C# class with various method types
        patch = """
@@ -73,9 +73,7 @@ public UserService(IUserRepository repository)

@@ -87,7 +87,8 @@ public async Task<User> GetUserAsync(int id)

@@ -95,6 +95,7 @@ public bool ValidateUser(User user)

@@ -103,4 +107,23 @@ private void LogUserAction(string action)

@@ -115,6 +118,13 @@ public static UserService CreateDefault()

@@ -125,7 +125,7 @@ protected virtual void OnUserChanged(UserEventArgs e)

@@ -135,8 +135,8 @@ public void Dispose()

@@ -145,10 +145,10 @@ ~UserService()

@@ -168,15 +168,15 @@ public int Count => _users.Count;

@@ -180,18 +180,18 @@ public User this[int index] => _users[index];

"""

        assert CSharpParser.extract_functions_from_patch(patch) == {
            "UserService",
            "GetUserAsync",
            "ValidateUser",
            "LogUserAction",
            "CreateDefault",
            "OnUserChanged",
            "Dispose",
            "Count",
        }

    def test_csharp_interface_implementations(self) -> None:
        patch = """
@@ -152,10 +152,6 @@ void IDisposable.Dispose()

@@ -152,10 +152,6 @@ string IFormattable.ToString(string format, IFormatProvider provider)

@@ -152,10 +152,6 @@ int IComparable<T>.CompareTo(T other)

@@ -152,10 +152,6 @@ bool IEquatable<T>.Equals(T other)

"""

        assert CSharpParser.extract_functions_from_patch(patch) == {
            "Dispose",
            "ToString",
            "CompareTo",
            "Equals",
        }

    def test_csharp_local_functions_and_nested(self) -> None:
        patch = """
@@ -152,10 +152,6 @@ void OuterMethod()
{
    void InnerFunction()
    {
        // local function inside method
    }
}

@@ -165,15 +165,15 @@ static int Calculate(int x)

@@ -175,18 +175,18 @@ async Task<string> ProcessDataAsync()

@@ -185,20 +185,20 @@ T GenericLocalFunction<T>(T input)

"""

        assert CSharpParser.extract_functions_from_patch(patch) == {
            "OuterMethod",
            "Calculate",
            "ProcessDataAsync",
            "GenericLocalFunction",
        }

    def test_csharp_edge_cases(self) -> None:
        patch = """
@@ -152,10 +152,6 @@ public unsafe void* GetPointer()

@@ -152,10 +152,6 @@ public extern static void ExternalMethod();

@@ -152,10 +152,6 @@ [Obsolete("Use NewMethod instead")]
public void OldMethod()

@@ -152,10 +152,6 @@ public partial void PartialMethod();

@@ -152,10 +152,6 @@ public virtual async Task<IEnumerable<T>> ComplexMethod<T>()

"""

        assert CSharpParser.extract_functions_from_patch(patch) == {
            "GetPointer",
            "ExternalMethod",
            "OldMethod",
            "PartialMethod",
            "ComplexMethod",
        }


class GoParserTestCase(TestCase):
    def test_go_simple(self) -> None:
        patch = """
@@ -152,10 +152,6 @@ func Hello(name string) string

@@ -152,10 +152,6 @@ func (r *Receiver) MethodName() error

@@ -152,10 +152,6 @@ func (r Receiver) ValueMethod() string

@@ -152,10 +152,6 @@ var myFunc = func() {

@@ -152,10 +152,6 @@ func Calculate(x, y int) int

@@ -152,10 +152,6 @@ func ProcessData() (string, error)

@@ -152,10 +152,6 @@ func noParams()

"""

        assert GoParser.extract_functions_from_patch(patch) == {
            "Hello",
            "MethodName",
            "ValueMethod",
            "myFunc",
            "Calculate",
            "ProcessData",
            "noParams",
        }

    def test_go_methods_with_receivers(self) -> None:
        patch = """
@@ -152,10 +152,6 @@ func (s *Server) Start() error

@@ -152,10 +152,6 @@ func (s Server) Stop()

@@ -152,10 +152,6 @@ func (h *Handler) ServeHTTP(w ResponseWriter, r *Request)

@@ -152,10 +152,6 @@ func (db *Database) Query(query string) (*Result, error)

@@ -152,10 +152,6 @@ func (u User) String() string

@@ -152,10 +152,6 @@ func (p *Point) Distance(q *Point) float64

"""

        assert GoParser.extract_functions_from_patch(patch) == {
            "Start",
            "Stop",
            "ServeHTTP",
            "Query",
            "String",
            "Distance",
        }

    def test_go_function_variables(self) -> None:
        patch = """
@@ -152,10 +152,6 @@ var handler = func(w http.ResponseWriter, r *http.Request) {

@@ -152,10 +152,6 @@ var callback = func() error {

@@ -152,10 +152,6 @@ processor := func(data []byte) []byte {

@@ -152,10 +152,6 @@ validator := func(input string) bool {

@@ -152,10 +152,6 @@ var transformer = func(x int) int {

@@ -152,10 +152,6 @@ mapper := func(items []string) map[string]int {

"""

        assert GoParser.extract_functions_from_patch(patch) == {
            "handler",
            "callback",
            "processor",
            "validator",
            "transformer",
            "mapper",
        }

    def test_go_interface_methods(self) -> None:
        # Note: Interface method regex is intentionally last in the list
        # because it's more general and could match other patterns
        patch = """
@@ -152,10 +152,6 @@ Read(p []byte) (n int, err error)

@@ -152,10 +152,6 @@ Write(p []byte) (n int, err error)

@@ -152,10 +152,6 @@ Close() error

@@ -152,10 +152,6 @@ String() string

@@ -152,10 +152,6 @@ ServeHTTP(ResponseWriter, *Request)

@@ -152,10 +152,6 @@ Validate() bool

"""

        assert GoParser.extract_functions_from_patch(patch) == {
            "Read",
            "Write",
            "Close",
            "String",
            "ServeHTTP",
            "Validate",
        }

    def test_go_real_world_example(self) -> None:
        # Based on a typical Go service with various function types
        patch = """
@@ -73,9 +73,7 @@ func NewService(db *sql.DB) *Service

@@ -87,7 +87,8 @@ func (s *Service) GetUser(ctx context.Context, id int) (*User, error)

@@ -95,6 +95,7 @@ func (s *Service) CreateUser(user *User) error

@@ -103,4 +107,23 @@ func validateEmail(email string) bool

@@ -115,6 +118,13 @@ var logger = func(msg string) {

@@ -125,7 +125,7 @@ func (s *Service) updateCache(key string, value interface{})

@@ -135,8 +135,8 @@ handleError := func(err error) {

@@ -145,10 +145,10 @@ func init()

@@ -168,15 +168,15 @@ func main()

"""

        assert GoParser.extract_functions_from_patch(patch) == {
            "NewService",
            "GetUser",
            "CreateUser",
            "validateEmail",
            "logger",
            "updateCache",
            "handleError",
            "init",
            "main",
        }

    def test_go_complex_signatures(self) -> None:
        patch = """
@@ -152,10 +152,6 @@ func Process(ctx context.Context, opts ...Option) (*Result, error)

@@ -152,10 +152,6 @@ func (c *Client) Do(req *Request) (*Response, error)

@@ -152,10 +152,6 @@ func HandleFunc(pattern string, handler func(ResponseWriter, *Request))

@@ -152,10 +152,6 @@ var middleware = func(next http.Handler) http.Handler {

@@ -152,10 +152,6 @@ converter := func(input interface{}) (interface{}, error) {

@@ -152,10 +152,6 @@ func Generic[T any](items []T) T

"""

        assert GoParser.extract_functions_from_patch(patch) == {
            "Process",
            "Do",
            "HandleFunc",
            "middleware",
            "converter",
            "Generic",
        }

    def test_go_edge_cases(self) -> None:
        patch = """

@@ -152,10 +152,6 @@ func (r *T) method_with_underscore()

@@ -152,10 +152,6 @@ var fn123 = func() {

@@ -152,10 +152,6 @@ camelCase := func() {

@@ -152,10 +152,6 @@ func MixedCase_With_Underscores()

"""

        assert GoParser.extract_functions_from_patch(patch) == {
            "method_with_underscore",
            "fn123",
            "camelCase",
            "MixedCase_With_Underscores",
        }

    def test_go_multiline_signatures(self) -> None:
        """Test Go functions with parameters and return types spanning multiple lines"""
        patch = """
@@ -152,10 +152,6 @@ func LongFunction(
    param1 string,
    param2 int,
    param3 []byte,
) (string, error)

@@ -160,12 +160,8 @@ func (s *Service) ProcessRequest(
    ctx context.Context,
    request *http.Request,
    options ...Option,
) (*Response, error) {

@@ -170,15 +170,10 @@ var complexHandler = func(
    w http.ResponseWriter,
    r *http.Request,
    middleware []Middleware,
) error {

@@ -180,18 +180,12 @@ transformer := func(
    input map[string]interface{},
    validators []Validator,
) (
    map[string]interface{},
    error,
) {

@@ -190,20 +190,15 @@ func GenericProcessor[T any, R comparable](
    items []T,
    processor func(T) R,
    options ProcessOptions,
) ([]R, error)

@@ -200,25 +200,18 @@ func (db *Database) ExecuteTransaction(
    ctx context.Context,
    queries []string,
    params []interface{},
) (
    results []Result,
    err error,
)

@@ -210,30 +210,20 @@ var middleware = func(
    next http.Handler,
) http.Handler {

@@ -215,35 +215,22 @@ MultilineInterface(
    param1 string,
    param2 int,
) (string, error)

"""

        assert GoParser.extract_functions_from_patch(patch) == {
            "LongFunction",
            "ProcessRequest",
            "complexHandler",
            "transformer",
            "GenericProcessor",
            "ExecuteTransaction",
            "middleware",
            "MultilineInterface",
        }

    def test_go_separate_variable_assignment(self) -> None:
        """Test Go function variables declared separately from assignment (addressing PR comment)"""
        patch = """
@@ -152,10 +152,6 @@ var add func(int, int) int
some other code here
@@ -160,12 +160,8 @@ add = func(x, y int) int {

@@ -170,15 +170,10 @@ var handler func(http.ResponseWriter, *http.Request)
@@ -175,18 +175,12 @@ handler = func(w http.ResponseWriter, r *http.Request) {

@@ -180,20 +180,15 @@ var processor func([]byte) []byte
random code
@@ -190,25 +190,18 @@ processor = func(data []byte) []byte {

"""

        # The separate assignment should be captured by function_assignment_regex
        assert GoParser.extract_functions_from_patch(patch) == {
            "add",
            "handler",
            "processor",
        }
