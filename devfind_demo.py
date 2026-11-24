"""DevFind — Semantic Bug & Issue Explorer.
Install: python -m pip install -U weaviate-client
Set WEAVIATE_URL and WEAVIATE_API_KEY in your terminal before running.
This classroom script deletes only the DevFindIssue collection at startup.
Do not use with real data.
"""
import os, sys
import weaviate
from weaviate.classes.init import Auth
from weaviate.classes.config import Configure, Property, DataType
from weaviate.classes.query import Filter

COLLECTION = "DevFindIssue"
SAMPLE_ISSUES = [
{"title":"Session expires on page reload","description":"After refreshing the dashboard, the user is redirected to the login page even though the session was active.","component":"Authentication","severity":"High","status":"Open","issue_key":"AUTH-101"},
{"title":"Login fails after token refresh","description":"The application returns an unauthorized error when an access token is refreshed during an active session.","component":"Authentication","severity":"Critical","status":"Open","issue_key":"AUTH-102"},
{"title":"Password reset email is delayed","description":"Password recovery messages arrive several minutes after the reset request is submitted.","component":"Authentication","severity":"Medium","status":"In Progress","issue_key":"AUTH-103"},
{"title":"Search page crashes on empty query","description":"Submitting the search form without text causes the results page to throw an exception.","component":"Search","severity":"High","status":"Open","issue_key":"SRCH-201"},
{"title":"Search results load slowly for large projects","description":"Searching a project with thousands of issues takes more than ten seconds to show results.","component":"Search","severity":"Medium","status":"In Progress","issue_key":"SRCH-202"},
{"title":"Avatar image is missing in profile","description":"The profile page shows a broken image icon when a user uploads a new avatar.","component":"User Profile","severity":"Low","status":"Open","issue_key":"USER-301"},
{"title":"Permission check allows viewer to edit settings","description":"A user with viewer permissions can open the settings screen and save changes.","component":"Authorization","severity":"Critical","status":"Open","issue_key":"AUTHZ-401"},
{"title":"CSV export omits records","description":"Exported CSV files do not include all rows when the issue list spans multiple pages.","component":"Reporting","severity":"Medium","status":"Resolved","issue_key":"REP-501"},
{"title":"Application logs out after browser refresh","description":"Refreshing a page unexpectedly clears the authentication state and ends the current session.","component":"Authentication","severity":"High","status":"Open","issue_key":"AUTH-104"},
{"title":"Mobile navigation menu will not close","description":"On narrow screens, tapping a navigation link does not dismiss the side menu.","component":"UI","severity":"Low","status":"Open","issue_key":"UI-601"},
]
def main():
    url=os.getenv("WEAVIATE_URL"); key=os.getenv("WEAVIATE_API_KEY")
    if not url or not key:
        sys.exit("Set WEAVIATE_URL and WEAVIATE_API_KEY environment variables first.")
    with weaviate.connect_to_weaviate_cloud(cluster_url=url, auth_credentials=Auth.api_key(key)) as client:
        print("Connected:", client.is_ready())
        if client.collections.exists(COLLECTION):
            client.collections.delete(COLLECTION)
        client.collections.create(name=COLLECTION, vector_config=Configure.Vectors.text2vec_weaviate(),
            properties=[
                Property(name="title",data_type=DataType.TEXT),
                Property(name="description",data_type=DataType.TEXT),
                Property(name="component",data_type=DataType.TEXT),
                Property(name="severity",data_type=DataType.TEXT),
                Property(name="status",data_type=DataType.TEXT),
                Property(name="issue_key",data_type=DataType.TEXT)])
        issues=client.collections.use(COLLECTION); ids={}
        for issue in SAMPLE_ISSUES: ids[issue["issue_key"]]=issues.data.insert(properties=issue)
        print("Inserted",len(SAMPLE_ISSUES),"issues.")
        one=issues.query.fetch_object_by_id(ids["AUTH-101"]); print("READ:",one.properties if one else None)
        print('SEMANTIC SEARCH: login breaks after refresh')
        for o in issues.query.near_text(query="login breaks after refresh",limit=5).objects:
            print(o.properties["issue_key"],"|",o.properties["title"],"|",o.properties["component"],"|",o.properties["severity"])
        print("FILTERED SEARCH: Authentication")
        filtered=issues.query.fetch_objects(filters=Filter.by_property("component").equal("Authentication"),limit=20)
        for o in filtered.objects: print(o.properties["issue_key"],"|",o.properties["title"])
        print("HYBRID SEARCH: session refresh login")
        for o in issues.query.hybrid(query="session refresh login",limit=5).objects:
            print(o.properties["issue_key"],"|",o.properties["title"])
        issues.data.update(uuid=ids["AUTH-103"],properties={"status":"Resolved","description":"Password recovery messages now arrive promptly after the reset request."})
        updated=issues.query.fetch_object_by_id(ids["AUTH-103"]); print("UPDATED:",updated.properties if updated else None)
        issues.data.delete_by_id(ids["UI-601"])
        print("Deleted successfully:",issues.query.fetch_object_by_id(ids["UI-601"]) is None)
        print("Demo complete.")
if __name__=="__main__": main()
