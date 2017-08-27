Docker
======

To run on docker, you have to add a ``.env`` file in the top level directory of the folder that looks something like
this:

.. code-block::

    # Add Environment Variables

    OCSPDASH_DEBUG=False
    OCSPDASH_SECRET_KEY=5(15ds+i2+%ik6z&!yer+ga9m=e%jcqiz_5wszg)r-z!2--b2d
    OCSPDASH_DB_NAME=postgres
    OCSPDASH_DB_USER=postgres
    OCSPDASH_DB_PASS=postgres
    OCSPDASH_DB_SERVICE=postgres
    OCSPDASH_DB_PORT=5432


Reference: https://realpython.com/blog/python/dockerizing-flask-with-compose-and-machine-from-localhost-to-the-cloud/
