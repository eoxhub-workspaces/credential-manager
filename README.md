# credential-manager

Small CRUD app to allow users to manage their own credentials.

# Frontend

* Existing Key-Value pairs are displayed.
* When adding a new Key-Value Pair, the `Key` input is **validated** (alphanumeric, starting with a letter).
* The `Value` input type is dynamically set to `password` if the credential has a `cm_keyonly` annotation.
* If the credential has the `cm_readonly` or `cm_keyonly` annotations:
  * both inputs (`Key` & `Value`) are set to **readonly**
  * the credential **cannot be deleted**

# Backend

## `my_credentials/__init__.py`

Basic **FastAPI** application with several key features related to **monitoring and logging**.

### Setup

```python
app = FastAPI()
app.add_middleware(PrometheusMiddleware)
app.add_route("/metrics", handle_metrics)
```
* An instance of the FastAPI application is created.
* It adds `PrometheusMiddleware` to the application. This middleware automatically collects metrics (like request duration, status codes, and request counts) for your API endpoints.
* It registers an endpoint at `/metrics` that Prometheus can scrape. The `handle_metrics` function processes and exposes the collected metrics data in a format Prometheus understands.

```python
if __name__ != "__main__":
  # ... logging setup ...
```
* This block ensures that if the application is run under a production web server like **Gunicorn** (which sets `__name__` to something other than `"__main__"`), it configures the application's logging to use **Gunicorn's existing log handlers and level**. This integrates the application logs seamlessly with the Gunicorn process logs.


### Infrastructure Endpoints

```python
INFRASTRUCTURE_VIEWS = ["/probe", "/metrics"]
```
* This list specifies endpoints that are typically used for infrastructure (health checks, monitoring) and should be excluded from the custom logging middleware (to prevent unnecessary log spam).

```python
@app.get("/probe")
def probe():
    return {}
```
* This defines a simple **health check** endpoint at `/probe`. It is used by load balancers, container orchestrators (like Kubernetes), or monitoring systems to check if the service is running and responsive.


### Custom Logging Middleware

```python
@app.middleware("http")
async def log_middle(request: Request, call_next):
    # ... logging logic ...
```
This is a **custom HTTP middleware** that runs for every incoming request.
  * It records the `start_time` before processing the request.
  * `response = await call_next(request)` passes the request to the rest of the application/route handlers and waits for the response.
  * It checks if the requested path is **NOT** in the `INFRASTRUCTURE_VIEWS` list.
  * If it's a regular request, it calculates the `duration` and logs a structured line containing:
      * **HTTP Method** (e.g., `GET`)
      * **URL**
      * **Duration** in milliseconds (e.g., `duration:15.34ms`)
      * **Content-Length** of the response
      * **HTTP Status Code** (e.g., `status:200`)


-----

## `my_credentials/views.py`

**FastAPI** application that acts as a simple web interface for managing **Kubernetes Secrets** within its own namespace.  
It allows a user to list, view, create, update, and delete secrets that are specifically labeled as belonging to this application.

### Setup

* `app` (the FastAPI instance) is imported from `my_credentials`
* **Jinja2** is initialized for server-side HTML rendering, assuming HTML files are located in a `templates` directory.

```python
MY_SECRETS_LABEL_KEY = "owner"
MY_SECRETS_LABEL_VALUE = "my-credentials"
```
* These constants define the Kubernetes label that all managed secrets must have. This ensures the application only interacts with secrets it is designated to control, preventing accidental modification of other secrets.

```python
@app.on_event("startup")
async def startup_load_k8s_config():
    # ... logic to load Kubernetes config ...
```
* This function runs once when the FastAPI application starts up. It tries to load the Kubernetes configuration, first using a local file (`load_kube_config`) for development, and then falling back to **in-cluster configuration** (`load_incluster_config`) for when the application is running inside a Kubernetes pod.

### Main Functions

`get_secret_list()`
 * Retrieves all `V1Secret` objects in the current namespace.
 * Applies a `label_selector` using `MY_SECRETS_LABEL_KEY=MY_SECRETS_LABEL_VALUE` to **filter** the list, only fetching the secrets managed by the application.
 * Returns a serialized list of secrets.

### Endpoints (Views)

##### 1. List Credentials (Read All)

  * **Path:** `GET /`
  * **Function:** `list_credentials`
  * **Action:**
      * Gets list of secrets.
      * Renders the `credentials.html` template.

##### 2. List Credentials API (Read All)

  * **Path:** `GET /get-credentials`
  * **Function:** `list_credentials_api`
  * **Action:**
      * Returns serialized list of secrets.

##### 3. View/Edit Credential Form (Read/New)

  * **Paths:** `GET /credentials-detail/{credential_name}` and `GET /credentials-detail/`
  * **Function:** `credentials_detail`
  * **Action:**
      * If `credential_name` is present, it reads the existing Secret using the Kubernetes client and prepares the data for the form.
      * If `credential_name` is empty, it prepares empty data for creating a **new** secret.
      * It renders the `credential_detail.html` template, showing the secret's data in an editable form.

##### 4. Create/Update Credential (Write)

  * **Paths:** `POST /credentials-detail/{credentials_name}` and `POST /credentials-detail/`
  * **Function:** `create_or_update`
  * **Action:**
      * It reads the form data submitted by the user and constructs a new `V1Secret` object.
      * The user-provided secret values are **Base64-encoded**:
        ```python
        data={
            key: base64.b64encode(value.encode()).decode()
            for key, value in zip(data.secret_key, data.secret_value)
        }
        ```
      * **If it's an update:** Keys that exist in the old secret but are missing in the new data are set to `None`, which is a method to explicitly **delete keys** within the existing Kubernetes Secret object.

##### 5. Delete Credential (Delete)

  * **Path:** `DELETE /credentials-detail/{credentials_name}`
  * **Function:** `delete_credentials`
  * **Action:**
      * It calls `ensure_secret_is_mine` to check ownership first.
      * It deletes the specified secret using `delete_namespaced_secret`.
      * It returns an empty response with a **204 No Content** status code, standard for successful deletion.


---

## Setup for local development & testing:

### Setup

```shell
python -m venv venv
. ./venv/bin/activate
pip install -r requirements.txt
```

### Run
```shell
uvicorn my_credentials:app --reload
```