# TurtleNetwork Node Payout

Automated payout script for TurtleNetwork node operators. This may work for Waves nodes as well but it has not been 
tested yet

Based partly on iammortimer's script - https://github.com/iammortimer/TN_LPoS_Payout

### Configuration and Usage

#### Requirements
- Python 3.8 (for pywaves)  
- requests==2.28.2  
- PyWaves==1.0.4  



Config File: 
- Rename config_example.json to config.json and modify as needed. 

```
{
    "node": "<insert your node address and port>",
    "address" : "<insert the address if your node>",
    "alias" : "<insert node alias (optional)>",
    "excludeListTN" : "<insert addresses that lease but you want to exclude>",
    "firstBlock" : 2000000,
    "startBlock" : 0,
    "endBlock" : 0,
    "apikey" : "<insert api key for your node>",
    "percentageOfFeesToDistribute" : 90,
    "minAmounttoPay" : 0,
    "blockStorage": "blocks.json",
    "paymentStorage": "payments.json",
    "doPayment" : 0,
    "privatekey" : "<insert private key for your wallet>",
    "telegramKey" : "<insert telegram bot API key>"
}
```