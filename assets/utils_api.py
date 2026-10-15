import requests
import logging
import json
from typing import Any


class ApiUtils:
  # Both keys are None while registering, a bare email gets a client_id, and the
  # client_id then gets an api_key. The endpoint reads a null the same as an absent one.
  def __init__(self, baseUrl: str, api_key: str | None, client_id: str | None):
    self.url = baseUrl
    # self.auth = {"Authorization":api_key}
    self.headers = {'Accept': 'application/json'}
    # self.auth = requests.auth.HTTPBasicAuth('api_key', api_key)
    self.client_id = client_id
    self.api_key = api_key

  def test(self) -> Any:
    response = requests.post(
      f"{self.url}/data", headers=self.headers
    )  # , auth=self.auth) # , files=files
    # response = requests.get(url, headers=self.auth)
    return response.json()

  # The payload is json on the way out and json on the way back, so both sides are Any.
  def post(self, endp: str, data: dict[str, Any]) -> dict[str, Any]:
    data.update({"client_id": self.client_id, "api_key": self.api_key})
    logging.debug(f" -> Submitting POST api call to /{endp} ... data: {data}")
    response = requests.post(
      f"{self.url}/{endp}", json=data, headers=self.headers
    )  # , auth=self.auth) # , files=files
    if response.status_code not in (200, 201, 202):
      raise Exception(
        f"The {endp} endpoint was not successful. ErrCode={response.status_code} ErrMsg={response.text} data={data}"
      )
    return response.json()

  def put(self, s3_url: str, fPath: str) -> None:  # uses s3-promise-link.
    with open(fPath, 'rb') as file:  # , buffering=0 ??#os.path.join(os.environ["DATA_PATH"], fPath)
      response = requests.put(
        s3_url, headers={"Content-Type": "application/octet-stream"}, data=file
      )  # , headers={"Content-Type":""}, files={"file":file})

    logging.info(response.status_code)  # , response.text)
    if response.status_code != 200:
      raise Exception(
        f"Upload to presigned-url did not succeed. code:{response.status_code} msg:{response.text}"
      )
    logging.info(f"Completed upload of {fPath} to {s3_url[0:100]}...")

  def getData(self) -> Any:
    data = {"client_id": self.client_id, "dset": "vmadd.address"}
    response = requests.post(
      f"{self.url}/data", json=json.dumps(data), headers=self.headers
    )  # , auth=self.auth) # , files=files
    # response = requests.get(url, headers=self.auth)
    return response.json()

  def getSupply(self) -> Any:
    data = {"client_id": self.client_id, "supply": "VLAT503"}
    response = requests.post(
      f"{self.url}/supply", data=data, headers=self.headers
    )  # , auth=self.auth) # , files=files
    # response = requests.get(url, headers=self.auth)
    return response.json()

  @staticmethod
  def download_file(s3url: str, fPath: str) -> None:
    headers = {"Accept": "application/octet-stream"}
    logging.debug(f"Downloading {fPath} from {s3url}")

    with requests.get(s3url, headers=headers, stream=True) as stream:
      stream.raise_for_status()
      with open(fPath, "wb") as file:
        for chunk in stream.iter_content(chunk_size=8192):
          file.write(chunk)
