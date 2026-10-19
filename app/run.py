"""Start a loopback server. PostgreSQL ensures only one worker processes jobs."""
import uvicorn

if __name__ == '__main__':
    uvicorn.run('app.main:create_app',factory=True,host='127.0.0.1',port=8787,access_log=False)
