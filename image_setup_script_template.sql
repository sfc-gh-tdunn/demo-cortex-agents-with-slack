-- 1. Set up the Database and Schema for the Image Repository
USE ROLE ACCOUNTADMIN;
CREATE DATABASE IF NOT EXISTS CORTEX_BOT_DB;
CREATE SCHEMA IF NOT EXISTS CORTEX_BOT_DB.APPS;
USE SCHEMA CORTEX_BOT_DB.APPS;

-- 2. Create the Image Repository
CREATE IMAGE REPOSITORY IF NOT EXISTS CORTEX_REPO;
-- SHOW IMAGE REPOSITORIES; 
-- Note the 'repository_url' from the command above. 
-- You will tag your Docker image with this URL. 
-- e.g. <org>-<account>.registry.snowflakecomputing.com/cortex_bot_db/apps/cortex_repo/cortex_slack_bot:latest

-- 3. Create Network Rules to allow outbound access to Slack and Snowflake
-- SPCS containers block outbound internet by default.
-- You need to allow traffic to Slack API and Websockets.

CREATE OR REPLACE NETWORK RULE SLACK_NETWORK_RULE
  MODE = EGRESS
  TYPE = HOST_PORT
  VALUE_LIST = ('slack.com', 'www.slack.com', 'api.slack.com', 'wss-primary.slack.com'); 
  -- Note: Socket mode connects to wss-*.slack.com. You might need to allow wildcard domains if your region supports it, 
  -- or monitor logs to see which WSS endpoint it tries to hit.

CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION SLACK_ACCESS_INTEGRATION
  ALLOWED_NETWORK_RULES = (SLACK_NETWORK_RULE)
  ENABLED = TRUE;

-- 4. Create Compute Pool (The VM that runs your container)
CREATE COMPUTE POOL IF NOT EXISTS CORTEX_POOL
  MIN_NODES = 1
  MAX_NODES = 1
  INSTANCE_FAMILY = CPU_X64_XS; -- Smallest instance type

-- Wait for the pool to be ACTIVE
-- SHOW COMPUTE POOLS;

-- 5. Create the Service
-- Make sure you have pushed the docker image before running this!
CREATE SERVICE CORTEX_SLACK_BOT_SERVICE
  IN COMPUTE POOL CORTEX_APP_POOL
  EXTERNAL_ACCESS_INTEGRATIONS = (SLACK_ACCESS_INTEGRATION)
  FROM SPECIFICATION $$
    spec:
      containers:
        - name: cortex-slack-bot
          image: /<database-name>/apps/<image-repo-name>/cortex_slack_bot:latest
          env:
            # Update these values with your actual credentials
            ACCOUNT: "<account-identifier>"
            HOST: "<account-identifier>.snowflakecomputing.com"
            DEMO_USER: "<username>"
            DEMO_USER_ROLE: "<role-name>"
            WAREHOUSE: "<warehouse>"
            AGENT_ENDPOINT: "https://<account-identifier>.snowflakecomputing.com/api/v2/databases/<database-name>/schemas/<schema-name>/agents/<agent-name>:run"
            SLACK_APP_TOKEN: "xapp-..."
            SLACK_BOT_TOKEN: "xoxb-..."
            PAT: "<ProgrammicAccessToken>"
          volumeMounts:
            - name: app-storage
              mountPath: /app/data
      volumes:
        - name: app-storage
          source: local
  $$;

-- 6. Check status
-- SELECT SYSTEM$GET_SERVICE_STATUS('CORTEX_SLACK_BOT_SERVICE');
-- SELECT SYSTEM$GET_SERVICE_LOGS('CORTEX_SLACK_BOT_SERVICE', 0, 'cortex-slack-bot');
```

### Steps to Deploy

1.  **Build the Docker Image**:
    Navigate to your folder in your terminal:
    ```bash
    docker build --platform linux/amd64 -t cortex_slack_bot:latest .
    ```
    *(Note: `--platform linux/amd64` is crucial because SPCS runs on Linux/AMD64. If you build on a Mac M1/M2/M3 without this, it will crash.)*

2.  **Login to Snowflake Registry**:
    ```bash
    docker login <your_registry_url> -u <username>
    ```

3.  **Tag and Push**:
    ```bash
    docker tag cortex_slack_bot:latest <your_registry_url>/cortex_slack_bot:latest
    docker push <your_registry_url>/cortex_slack_bot:latest
    ```

4.  **Upload the Spec**:
    The `CREATE SERVICE` command in step 5 of the SQL script looks for `service_spec.yml` inside the `@CORTEX_REPO` stage. You need to upload the YAML file to Snowflake.
    * You can use Snowsight (Data -> Databases -> Stages).
    * Or use SnowSQL: `PUT file://service_spec.yml @CORTEX_REPO AUTO_COMPRESS=FALSE;`

5.  **Run the SQL**:
    Execute step 5 in the SQL script to spin up the service.

### Troubleshooting Network Access

Since you are using **Socket Mode**, the bot initiates a WebSocket connection to Slack (`wss://...`).
If the bot starts but immediately crashes or hangs, check the logs:
```sql
SELECT SYSTEM$GET_SERVICE_LOGS('CORTEX_SLACK_BOT_SERVICE', 0, 'cortex-slack-bot');