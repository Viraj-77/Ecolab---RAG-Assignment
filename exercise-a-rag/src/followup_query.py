import json  
import requests  
import urllib3  

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)  #stop ssl warning print


#this json format is instruction to llm about a tool when to use and what it should pass (because OPENAI NEEDS THIS FORMAT)
USGS_TOOL = {
    "type": "function",  
    "function": {
        "name": "get_water_quality",  #this is what the LLM calls when it wants to use this tool
        "description": (
            "Fetch recent water quality measurements from the USGS "  
            "for a given US state and a parameter such as pH, nitrate, or dissolved oxygen. "
            "Use this ONLY when the user asks for real, current, or location-specific " 
            "water quality readings. Do NOT call it for general or conceptual questions."  
        ),
        "parameters": {
            "type": "object",  #openai always requires object
            "properties": {  #these are arguements i.e state fips and parameters
                "state_fips": {
                    "type": "string",  #every us state has a 2 digit number that is used by LLM to understand
                    "description": "Two-digit FIPS state code, e.g. '27' for Minnesota, '48' for Texas.",  
                },
                "parameter": {
                    "type": "string",   #water quality metrics
                    "description": "Water quality parameter name as-is, e.g. 'pH', 'Nitrate', 'Temperature'.", 
                },
            },
            "required": ["state_fips"],  #state fips must be provided, parameter is optional and defaults to pH
        },
    },
}

ALL_TOOLS = [USGS_TOOL]  #list of all tools  and rag_pipeline.py imports this and passes it to the llm


def execute_tool(name, arguments):
    try:
        args = json.loads(arguments)  #llm sends arguments as a JSON string, convert it to a dict
    except:
        return json.dumps({"error": "couldn't parse arguments"})  #if parsing fails, return an error

    if name == "get_water_quality":  #check which tool the LLM called
        return _fetch_water_quality(**args)  #unpack the dict and pass as keyword arguments

    return json.dumps({"error": f"no tool called {name}"})  #if tool name doesn't match anything we have



#this dict maps names to those codes
PARAM_CODES = {
    "ph": "00400",           
    "temperature": "00010",  
    "temp": "00010",         
    "nitrate": "00630",      
    "dissolved oxygen": "00300",  
    "do": "00300",           
    "conductance": "00095",  
    "turbidity": "63680",    
}


def _fetch_water_quality(state_fips, parameter="pH"):
    param_code = PARAM_CODES.get(parameter.strip().lower(), "00400")  

    try:
        res = requests.get(
            "https://waterservices.usgs.gov/nwis/iv/",  #endpoint
            params={
                "format": "json",               
                "stateCd": state_fips.strip(),  
                "parameterCd": param_code,      
                "siteStatus": "active",         #take from active sites only
                "period": "P1D",                #last 1day of data
            },
            timeout=30,       
            verify=False,     
        )
        

        sites = res.json().get("value", {}).get("timeSeries", [])  #dig into the nested JSON to get the list of sites

        if not sites:  
            return json.dumps({"message": "no results found", "parameter": parameter})

        records = []
        for site in sites[:5]:  #only look at first 5 sites, enough for the llm to summarize
            readings = site.get("values", [{}])[0].get("value", []) 
            last = readings[-1] if readings else {}  #take the latest value or give blank
            records.append({
                "site": site.get("sourceInfo", {}).get("siteName", "?"),          #site name
                "value": last.get("value", "N/A"),                                 #actiual measurement
                "unit": site.get("variable", {}).get("unit", {}).get("unitCode", ""),  
                "time": last.get("dateTime", ""),                                  
            })

        return json.dumps({"parameter": parameter, "records": records})  #send the results back to llm

    except Exception as e:
        return json.dumps({"error": str(e)})  #error occurs then show message 