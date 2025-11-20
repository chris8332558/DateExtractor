'''
Test file for wayback cdx server apis.
The repo is here: https://github.com/internetarchive/wayback/tree/master/wayback-cdx-server
'''

import requests



if __name__ == "__main__":
    Target_URL = "https://www.usip.org/publications/2021/04/enhancing-us-china-strategic-stability-era-strategic-competition"

    # Only required param for the CDX server is the 'url' param. All other params are optional
    # The 'url' should be 'url encoded' if the url itself contains a query
    # res = requests.get(f"http://web.archive.org/cdx/search/cdx?url={Target_URL}")
    # print("\n===========\n")
    # print(res.content)
    # print(res.text)
    


    # Output format (JSON) and Limit
    # res = requests.get(f"http://web.archive.org/cdx/search/cdx?url={Target_URL}&output=json&limit=3")
    # print("\n===========\n")
    # print(res.json())

    
    # Response Field Order (Only return the specified fileds in the 'fl=' param)
    # res = requests.get(f"http://web.archive.org/cdx/search/cdx?url={Target_URL}&fl=original,timestamp,mimetype&output=json&limit=3")
    # print("\n===========\n")
    # print(res.json())

    # Filtering (Can filter Date Range, status code, and mime type)
    ## Filter Date Range (It captures: yyyyMMddhhmmss. e.g. '&from=2010&to=2011')
    res = requests.get(f"http://web.archive.org/cdx/search/cdx?url={Target_URL}&fl=original,timestamp,mimetype&output=json&limit=3&from=2023&to=2025")
    print("\n===========\n")
    print(res.json())
    
    ## Filter NOT matches with '!' 
    # res = requests.get(f"http://web.archive.org/cdx/search/cdx?url={Target_URL}&output=json&limit=3&filter=!statuscode:200&filter=!mimetype:text/html")
    # print("\n===========\n")
    # print(res.json())

    