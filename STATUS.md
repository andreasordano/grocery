# pantryrun: status

Plans, tasks, decisions and notes live in Atlassian, not in this file:

- **Roadmap and knowledge:** Confluence space [Pantryrun](https://pantryrun.atlassian.net/wiki/spaces/PR/overview)
  ([Roadmap](https://pantryrun.atlassian.net/wiki/spaces/PR/pages/294913/Roadmap),
  [Decisions](https://pantryrun.atlassian.net/wiki/spaces/PR/pages/524290/Decisions),
  [Kill criteria and metrics](https://pantryrun.atlassian.net/wiki/spaces/PR/pages/262340/Kill+criteria+and+metrics))
- **Tasks:** Jira [WEB](https://pantryrun.atlassian.net/jira/software/projects/WEB) (the app),
  [DATA](https://pantryrun.atlassian.net/jira/software/projects/DATA) (metrics and price data),
  [PROD](https://pantryrun.atlassian.net/jira/software/projects/PROD) (validation and business)

Live at https://grocery-j3en.onrender.com (Render web service `groceries-api`, deploys `main`; database on Supabase, project `tafaiatzpjpvkdoazwiz`, Frankfurt).

## Picking it up again
```bash
docker compose up --build -d                 # app at http://localhost:8000/?u=yourname
python -m pytest -q tests                    # 94 tests (+9 browser tests with requirements-dev.txt)
python -m scripts.healthcheck                # are the stores and rules still OK?
docker compose exec db psql -U groceries     # look at events (queries in README.md)

# Look at the data in the browser (read-only): local on :8081, production on :8082
docker run --rm -p 127.0.0.1:8081:8081 sosedoff/pgweb --readonly \
  --url "postgres://groceries:groceries@host.docker.internal:5433/groceries?sslmode=disable"
docker run --rm -p 127.0.0.1:8082:8081 sosedoff/pgweb --readonly \
  --url "<Supabase session pooler URL>?sslmode=require"
```

After changing Python code, run `docker compose restart api`: the container doesn't reload, and the page
then loads without its CSS and JS.
