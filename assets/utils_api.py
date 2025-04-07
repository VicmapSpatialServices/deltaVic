import requests, logging, json

class ApiUtils():
  def __init__(self, baseUrl, api_key, client_id):
    self.url = baseUrl
    # self.auth = {"Authorization":api_key}
    self.headers = {'Accept': 'application/json'}
    # self.auth = requests.auth.HTTPBasicAuth('api_key', api_key)
    self.client_id = client_id
    self.api_key = api_key

  def test(self):
    response = requests.post(f"{self.url}/data", headers=self.headers)#, auth=self.auth) # , files=files
    # response = requests.get(url, headers=self.auth)
    return response.json()

  def post(self, endp:str, data:dict):
    data.update({"client_id":self.client_id,"api_key":self.api_key})
    logging.debug(f" -> Submitting POST api call to /{endp}")
    response = requests.post(f"{self.url}/{endp}", json=data, headers=self.headers)#, auth=self.auth) # , files=files
    if response.status_code != 200:
      raise Exception(f"The {endp} endpoint was not successful. ErrCode={response.status_code} ErrMsg={response.text}")
    return response.json()

  def put(self, s3_url, fPath): # uses s3-promise-link.
    with open(fPath, 'rb') as file: #, buffering=0 ??#os.path.join(os.environ["DATA_PATH"], fPath)
      response = requests.put(s3_url, headers={"Content-Type":"application/octet-stream"}, data=file)#, headers={"Content-Type":""}, files={"file":file})
    
    logging.info(response.status_code)#, response.text)
    if response.status_code != 200:
      raise Exception(f"Upload to presigned-url did not succeeed. code:{response.status_code} msg:{response.text}")
    logging.info(f"Completed upload of {fPath} to {s3_url[0:100]}...")
    
  def getData(self):
    data = {"client_id":self.client_id,"dset":"vmadd.address"}
    response = requests.post(f"{self.url}/data", json=json.dumps(data), headers=self.headers)#, auth=self.auth) # , files=files
    # response = requests.get(url, headers=self.auth)
    return response.json()

  def getSupply(self):
    data = {"client_id":self.client_id,"supply":"VLAT503"}
    response = requests.post(f"{self.url}/supply", data=data, headers=self.headers)#, auth=self.auth) # , files=files
    # response = requests.get(url, headers=self.auth)
    return response.json()
  
  @staticmethod
  def download_file(s3url, fPath):
    headers = {"Accept":"application/octet-stream"}
    logging.debug(f"Downloading {fPath} from {s3url}")
    
    with requests.get(s3url, headers=headers, stream=True) as stream:
      stream.raise_for_status()
      with open(fPath, "wb") as file:
        for chunk in stream.iter_content(chunk_size=8192):
          file.write(chunk)


  