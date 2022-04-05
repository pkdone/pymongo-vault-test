# PyMongo Vault Test

A simple tool for testing MongoDB [Self-Managed](https://www.mongodb.com/docs/manual/) or [Atlas](https://www.mongodb.com/docs/atlas/) database user integration with [HashiCorp Vault](https://www.vaultproject.io/) from the perspective of a client application using one of the [MongoDB Drivers](https://www.mongodb.com/docs/drivers/) (PyMongo in this case).

This project assumes you are an experienced MongoDB and Atlas user and have at least a little bit of experience with HashiCorp Vault. If you have no experience with using HashiCorp Vault, it is recommended that you first try the following blog post tutorial: [Manage MongoDB Atlas Database Secrets in HashiCorp Vault](https://www.mongodb.com/blog/post/manage-atlas-database-secrets-hashicorp-vault).

The rest of this README describes how to use this tool to test MongoDB database secrets management for both "dynamic" and "static" database users with both your own self-managed database deployment (using the [MongoDB Database Secrets Engine](https://www.vaultproject.io/docs/secrets/databases/mongodb) plug-in for Vault) and your Atlas deployed database cluster (using the [MongoDB Atlas Database Secrets Engine](https://www.vaultproject.io/docs/secrets/databases/mongodbatlas) plug-in for Vault).


## Prerequisites

You have the following configured:

 - [HashiCorp Vault is installed](https://www.vaultproject.io/downloads) on your local workstation
 - [MongoDB is installed](https://www.mongodb.com/docs/manual/installation/) on your local workstation and running with the following configuration:
    - [SCRAM Authentication is enabled](https://www.mongodb.com/docs/manual/tutorial/configure-scram-client-authentication/)
    - An *admin user* has been created in the `admin` database via the [MongoDB Shell](https://www.mongodb.com/docs/mongodb-shell/), using a command similar to the following:
        ```javascript
        use admin;
        
        // Create Admin User
        db.createUser(
          {
            user: "administrator",
            pwd: "Password1",
            roles: [
              { role: "userAdminAnyDatabase", db: "admin" },
              { role: "readWriteAnyDatabase", db: "admin" }
            ]
          }
        );
        ```    
    - An *database user admin user* has been created in the `testdb` database via the [MongoDB Shell](https://www.mongodb.com/docs/mongodb-shell/), using a command similar to the following to allow only user management of users in the `testdb` database:
        ```javascript
        use testdb;
        
        // Create TestDB User Admin User
        db.createUser(
          {
            user: "testDBUserAdmin",
            pwd: "testpwd1",
            roles: [
              { role: "userAdmin", db: "testdb" }
            ]
          }
        );
        ```    
    - A *normal database application user* has been created in the `testdb` database via the [MongoDB Shell](https://www.mongodb.com/docs/mongodb-shell/) to be able to read and write to the `testdb` database only, using a command similar to the following:
        ```javascript
        use testdb;
        
        // Create App User
        db.createUser(
          {
            user: "myapp-user",
            pwd: "abc123",
            roles: [
              { role: "readWrite", db: "testdb" }
            ]
          }
        );
        ```    
    - Python 3 and the PyMongo driver and Vault Python library have been installed on your workstation, e.g.:
        ```console
        pip3 install --user pymongo hvac
        ```
 - [An Atlas cluster is deployed](https://www.mongodb.com/docs/atlas/getting-started/) in the cloud with the following set:
    - Your [Connection IP Address is added to the IP Access List](https://www.mongodb.com/docs/atlas/security/add-ip-address-to-list/)
    - An [Atlas Database User is created for your Cluster](https://www.mongodb.com/docs/atlas/tutorial/create-mongodb-user-for-cluster/) called **myapp-user** where just one database user privilege is defined for this new user, by assigning **readWrite@testdb** in  **Specific Privileges** (to ensure this user can only read and write to a database called `testdb`)
    - An [Atlas Admin API Key is created for your Atlas Project](https://www.mongodb.com/docs/atlas/tutorial/configure-api-access/project/create-one-api-key/) assigned with the role **Project Owner**


## Vault Configuration

In **one terminal**, start the _vault_ server in development mode, via the command:

```console
vault server -dev
```

_NOTE:_ When starting Vault in development mode as shown here, Vault's root token will be automatically saved to `~/.vault-token` for your current host OS user. Assuming you will be running the client application using this same host OS user, this will allow the tests to work with the client application able to access any resources it wants from the current Vault server. However, for Production environments you should not use the root token for Vault access, you should restrict the scope of the client application's access to Vault resource to the bare minimum, and you should follow HashiCorp Vault's [Production Hardening]{https://learn.hashicorp.com/tutorials/vault/production-hardening) best practices. 

Keep the Vault process running in the first terminal and start a **second terminal** to use for the rest of the Vault configuration steps and Python tests in this README.

Configure the new terminal environment to reference the locally running Vault development server:

```console
export VAULT_ADDR='http://127.0.0.1:8200'
```

Enable the Vault Database Secrets Engine:

```console
vault secrets enable database
```

In the next sections you will configure database related secrets in Vault in a Development environment. In Production, the Vault identity allowed to create these secrets should be restricted and different to the subsequent identity used by a client application which tries to read one of these secrets. This will ensure that client application cannot _overstep its mark_ and access parts of a database it shouldn't be allowed to. For more information, see [Vault Authentication](https://www.vaultproject.io/docs/concepts/auth) and [Vault Policies](https://www.vaultproject.io/docs/concepts/policies). 


### Vault Configuration for the Self-Managed Local MongoDB Deployment

Configure Vault's _MongoDB Database Secrets Engine_ to know how to:
 1. Connect to the self-managed local database to create and access users
 2. Create a dynamic role to enable a database user to be created on the fly
 3. Create a static role which will enable an pre-existing database user to be used and password rotated:

_(Note, first change the connection string `localhost:27017` to match your local MongoDB listen address, if required)_


```console
# MongoDB Database Secrets Engine configuration
vault write database/config/selfmngd-mongodb-testdb \
    plugin_name=mongodb-database-plugin \
    allowed_roles="myapp1-rw-role, myapp1-user-role" \
    connection_url="mongodb://{{username}}:{{password}}@localhost:27017/testdb" \
    username="testDBUserAdmin" \
    password="testpwd1"

# Define a Dynamic database role for MongoDB
vault write database/roles/myapp1-rw-role \
    db_name=selfmngd-mongodb-testdb \
    creation_statements='{ "db": "testdb", "roles": [{"db": "testdb", "role": "readWrite"}]}' \
    default_ttl="1h" \
    max_ttl="24h"

# Define a Static database (user) role for MongoDB
vault write database/static-roles/myapp1-user-role \
  db_name=selfmngd-mongodb-testdb \
  username="myapp-user" \
  rotation_period=86400
```


### Vault Configuration for the Atlas Cluster Deployed to the Cloud

Configure Vault's _MongoDB Atlas Database Secrets Engine_ to know how to:
 1. Connect to the Atlas database to create and access users
 2. Create a dynamic role to enable a database user to be created on the fly
 3. Create a static role which will enable an pre-existing database user to be used and password rotated:

```console
# Atlas Database Secrets Engine configuration
vault write database/config/atlas-mongodb-testdb \
  plugin_name=mongodbatlas-database-plugin \
  allowed_roles="myapp2-rw-role, myapp2-user-role" \
  public_key="oldyopcx" \
  private_key="ef87e1ed-3b8a-485e-9926-35c1b9c493d7" \
  project_id="5aaf9f1cd383ad760d5c303b"

# Define a Dynamic database role for Atlas
vault write database/roles/myapp2-rw-role \
  db_name=atlas-mongodb-testdb \
  creation_statements='{"database_name": "admin", "roles":[{"databaseName":"testdb", "roleName":"readWrite"}]}' \
  default_ttl="1h" \
  max_ttl="24h"

# Define a Static database (user) role for Atlas
vault write database/static-roles/myapp2-user-role \
  db_name=atlas-mongodb-testdb \
  username="myapp-user" \
  rotation_period=86400
```


## Running the Test Python Application

This section will use the provider Python script `pymongo-vault-test.py`. To view all the parameters available for executing the script, run the following:

```console
./pymongo-vault-test.py -h
```


### Test the Local Self-Managed MongoDB Deployment


#### Dynamic Role User Test

Execute the Python test script twice in quick succession, to use a dynamic Vault role which will create a new user with new password for each execution (first change the connection string `localhost:27017` to match your local MongoDB listen address, if required):

```console
./pymongo-vault-test.py -u 'mongodb://localhost:27017' -r 'database/creds/myapp1-rw-role' -a testdb
./pymongo-vault-test.py -u 'mongodb://localhost:27017' -r 'database/creds/myapp1-rw-role' -a testdb
```

Notice in the output, a **new** database user (with new password) is created every time. 

Using the MongoDB Shell, connect to the database and view the list of users to observe that **two new users** have been created (first change the connection string `localhost:27017` to match your local MongoDB listen address, if required):

```console
mongosh "mongodb://localhost:27017" --username testDBUserAdmin --password testpwd1 --authenticationDatabase testdb
```

```javascript
use testdb;
db.getUsers();
exit;
```


#### Static Role User Test

Execute the Python test script three times in quick succession, with a password rotation command issued in-between, to use a static Vault role which relies on the user already existing in the database and to retrieve its username and current password (first change the connection string `localhost:27017` to match your local MongoDB listen address, if required):

```console
./pymongo-vault-test.py -u 'mongodb://localhost:27017' -r 'database/static-creds/myapp1-user-role' -a testdb
./pymongo-vault-test.py -u 'mongodb://localhost:27017' -r 'database/static-creds/myapp1-user-role' -a testdb
vault write -f database/rotate-role/myapp1-user-role
./pymongo-vault-test.py -u 'mongodb://localhost:27017' -r 'database/static-creds/myapp1-user-role' -a testdb
```

Notice in the output, the **same** database user is used each time, but for the third time a **different password** has been used, because it had been rotated. 

Using the MongoDB Shell, connect to the database and view the list of users to observe that **no new user** was created for `myapp-user` (first change the connection string `localhost:27017` to match your local MongoDB listen address, if required):

```console
mongosh "mongodb://localhost:27017" --username testDBUserAdmin --password testpwd1 --authenticationDatabase testdb
```

```javascript
use testdb;
db.getUsers();
exit;
```


### Test the Cloud Atlas Cluster


#### Dynamic Role User Test

Execute the Python test script twice in quick succession, to use a dynamic Vault role which will create a new user with new password for each execution (first change the connection string `mycluster.a123z.mongodb.net` to match your Atlas cluster SRV address):

```console
./pymongo-vault-test.py -u 'mongodb+srv://mycluster.a123z.mongodb.net/' -r 'database/creds/myapp2-rw-role'
./pymongo-vault-test.py -u 'mongodb+srv://mycluster.a123z.mongodb.net/' -r 'database/creds/myapp2-rw-role'
```

Notice in the output, a **new** database user (with new password) is created every time and in each case, before a successful database connection is made, a number of authentication errors occur (this happens because Atlas is asynchronously provisioning the database user, which typically takes around 10-30 seconds to complete).

Go to the [Atlas Console](https://cloud.mongodb.com), and for your Atlas Project select the **SECURITY | Database Access** link and in the shown **Database Users** page, observe that **two new users** have been created.



#### Static Role User Test

Execute the Python test script three times in quick succession, with a password rotation command issued in-between, to use a static Vault role which relies on the user already existing in the database and to retrieve its username and current password (first change the connection string `mycluster.a123z.mongodb.net` to match your Atlas cluster SRV address):

```console
./pymongo-vault-test.py -u 'mongodb+srv://mycluster.a123z.mongodb.net/' -r 'database/static-creds/myapp2-user-role'
./pymongo-vault-test.py -u 'mongodb+srv://mycluster.a123z.mongodb.net/' -r 'database/static-creds/myapp2-user-role'
vault write -f database/rotate-role/myapp2-user-role
./pymongo-vault-test.py -u 'mongodb+srv://mycluster.a123z.mongodb.net/' -r 'database/static-creds/myapp2-user-role'
```

Notice in the output, the **same** database user is used each time, but for the third execution a **different password** has been used, because it had been rotated. Also, notice that only for this third execution, before a successful database connection is made, a number of authentication errors occur. This happens because Atlas is asynchronously changing the database user's password due to the _rotation_ command having been executed just before it.

Go to the [Atlas Console](https://cloud.mongodb.com), and for your Atlas Project select the **SECURITY | Database Access** link and in the shown **Database Users** page, observe that **no new users** had been created for `myapp-user`.

