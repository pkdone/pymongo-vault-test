#!/usr/bin/python3
##
# A simple tool for testing MongoDB Self-Managed or Atlas database user integration with HashiCorp
# Vault from the perspective of a client application using one of the MongoDB drivers (PyMongo in
# this case).
#
# For usage first ensure the '.py' script is executable and then run:
#  $ ./pymongo-vault-test.py -h
#
# Example:
#  $ /pymongo-vault-test.py -u 'mongodb+srv://clstr.abc.mongodb.net/' -r 'database/creds/myapp-role'
#
# Prerequisites:
# * Install PyMongo driver & Vault library, eg:
#  $ pip3 install --user pymongo hvac
##
import sys
import hvac
import time
from argparse import ArgumentParser
from datetime import datetime
from pprint import pprint
from pymongo import MongoClient
from pymongo.errors import OperationFailure


##
# Main function to parse passed-in process before invoking the core processing function.
##
def main():
    argparser = ArgumentParser(description="A simple tool for testing MongoDB Self-Managed or Atlas"
                                           " database user integration with HashiCorp Vault from "
                                           "the perspective of a client application using one of "
                                           "the MongoDB drivers (PyMongo in this case)")
    argparser.add_argument("-u", "--url", default=DEFAULT_MONGODB_URL,
                           help=f"MongoDB cluster URL (default: {DEFAULT_MONGODB_URL})")
    argparser.add_argument("-r", "--rolepath", default=DEFAULT_VAULT_DB_ROLE,
                           help=f"Vault role path secret (default: {DEFAULT_VAULT_DB_ROLE})")
    argparser.add_argument("-a", "--authdb", default=DEFAULT_AUTHDBNAME,
                           help=f"Authentication database name (default: {DEFAULT_AUTHDBNAME})")
    argparser.add_argument("-d", "--db", default=DEFAULT_DBNAME,
                           help=f"Database name to hold data (default: {DEFAULT_DBNAME})")
    argparser.add_argument("-c", "--coll", default=DEFAULT_COLLNAME,
                           help=f"Collection name (default: {DEFAULT_COLLNAME})")
    args = argparser.parse_args()
    print(f"\nStarting task at {datetime.now().strftime(DATE_TIME_FORMAT)}")
    start = datetime.now()
    run(args.url, args.rolepath, args.authdb, args.db, args.coll)
    end = datetime.now()
    print(f"\nFinished task in {int((end-start).total_seconds())} seconds")
    print()


##
# Connect with the MongoDB database using authentication credentials sourced from Vault and then
# test inserting and querying a collection in the database.
##
def run(url, rolepath, authdb, dbname, collname):
    (username, password) = getDBCredentials(rolepath)
    print(f"\nConnecting to MongoDB using URL '{url}'")
    connection = MongoClient(url, username=username, password=password, authSource=authdb)
    coll = connection[dbname][collname]
    executedOk = False
    lastAuthErr = None

    for i in range(ATTEMPT_LIMIT):
        try:
            coll.insert_one({"a": 1})
            result = coll.find_one()
            print(f"\nResult from test collection insert() then find():")
            pprint(result)
            coll.delete_many({})
            executedOk = True
            break
        except OperationFailure as e:
            if e.code == 8000:  # 8000 equals authentication error
                print(f"\nAuthentication error, retrying because database service may still be "
                      f"implementing the user change")
                lastAuthErr = e
                time.sleep(WAIT_TIME_SECS)
            else:
                sys.exit(f"\nERROR: Unexpected MongoDB error:  {e}\n")

    if not executedOk:
        sys.exit(f"\nERROR: Gave up trying to authenticate with a MongoDB deployment. Last "
                 f"authentication error's detail:  {lastAuthErr}\n")


##
# Get the database user credentials (username & password) from HashiCorp Vault (assumes local
# environment is setup with the required context to successfully connect to the Vault process with
# an appropriate authentication token in place.
##
def getDBCredentials(rolepath):
    vaultClient = hvac.Client()
    response = vaultClient.read(rolepath)
    # pprint(response)
    username = response.get("data").get("username")
    password = response.get("data").get("password")
    print(f"\nObtained database credentials from Vault: {username=}, {password=}")
    return (username, password)


# Constants
DEFAULT_MONGODB_URL = "mongodb+srv://mycluster.a123z.mongodb.net/"
DEFAULT_VAULT_DB_ROLE = "database/creds/my-role"
DEFAULT_AUTHDBNAME = "admin"
DEFAULT_DBNAME = "testdb"
DEFAULT_COLLNAME = "mycoll"
DATE_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
ATTEMPT_LIMIT = 25
WAIT_TIME_SECS = 2


##
# Main
##
if __name__ == "__main__":
    main()
