# Script by TheNerd (aka TheNerd386) - https://github.com/thenerd
# Based partially on code written by iammortimer (TN_LPoS_Payout) - https://github.com/iammortimer/TN_LPoS_Payout
# Thanks Morty!

import requests
import json
import datetime
import pywaves as pw

# load config file
with open('config.json') as json_file:
    config = json.load(json_file)

# initialize a few variables
myLeases = {}
myCanceledLeases = {}
myForgedBlocks = []
payments = {}
totalfee = 0
paymentFile = config['paymentStorage']

# here's where you set what you pay out
amtNERD = 250000000000  # 2500 weekly
amtCOOL = 125000  # 125 weekly (COOL only uses 3 decimals)
amtHT = 0.1  # 10% of TN

# we use this txt file to store the last block we used during the previous run.
with open('start_block.txt', 'r') as f:
    startBlock = int(f.read())

# make sure to increment startBlock by 1, so we don't pay out twice for that one block
startBlock = startBlock + 1

print(f"Start Block is {startBlock}\n")


# function to clean up the data and remove what we don't need
def cleanBlocks(blocksJSON):
    for block in blocksJSON:

        if 'totalFee' in block:
            block['fee'] = block['totalFee']

        block.pop('nxt-consensus', None)
        block.pop('version', None)
        block.pop('features', None)
        block.pop('blocksize', None)
        block.pop('signature', None)
        block.pop('reference', None)
        block.pop('transactionCount', None)
        block.pop('generatorPublicKey', None)
        block.pop('desiredReward', None)
        block.pop('timestamp', None)
        block['transactions'] = [transaction for transaction in block['transactions'] if
                                 transaction['type'] == 8 or transaction['type'] == 9]
    return blocksJSON


# gotta catch em all
def getAllBlocks():
    startblock = config['firstBlock']
    steps = 100
    blocks = []

    # determine endBlock - should be able to remove if because we always want to use dynamic endblock
    if config['endBlock'] == 0:
        endBlock = requests.get(config['node'] + '/blocks/height').json()['height'] - 1
    else:
        endBlock = config['endBlock']

    # try to load previous processed blocks
    try:
        with open(config['blockStorage'], 'r') as f:
            blocks = json.load(f)

        startblock = blocks[len(blocks) - 1]['height'] + 1
        print('Snagged Blocks From ' + str(blocks[0]['height']) + ' to ' + str(startblock - 1))
    except Exception as e:
        print('no previous blocks file found')

    # retrieve blocks
    while (startblock < endBlock):
        if (startblock + (steps - 1) < endBlock):
            print('Grabbing Blocks From ' + str(startblock) + ' to ' + str(startblock + (steps - 1)))
            blocksJSON = requests.get(config['node'] + '/blocks/seq/' + str(startblock) + '/' + str(startblock + (steps - 1))).json()
        else:
            print('Grabbing Blocks From ' + str(startblock) + ' to ' + str(endBlock))
            blocksJSON = requests.get(config['node'] + '/blocks/seq/' + str(startblock) + '/' + str(endBlock)).json()

        # clear payed tx
        if (startblock + (steps - 1)) < startBlock:
            for block in blocksJSON:
                txs = []

                if block['height'] < startBlock:
                    for tx in block['transactions']:
                        if tx['type'] == 8 or tx['type'] == 9:
                            txs.append(tx)
                else:
                    txs = block['transactions']

                block['transactions'] = txs

        blocks += cleanBlocks(blocksJSON)

        if (startblock + steps < endBlock):
            startblock += steps
        else:
            startblock = endBlock

    return blocks


# checking for blocks we generate and leases that are active and cancelled
def prepareDataStructure(blocks):
    global myLeases
    global myCanceledLeases
    global myForgedBlocks
    prevBlock = None

    for block in blocks:
        fee = 0

        if block['generator'] == config['address']:
            myForgedBlocks.append(block)

        for tx in block['transactions']:
            if (tx['type'] == 8) and (tx['recipient'] == config['address'] or tx['recipient'] == 'address:' + config['address'] or tx['recipient'] == 'alias:L:' + config['alias']):
                tx['block'] = block['height']
                myLeases[tx['id']] = tx
            elif (tx['type'] == 9) and (tx['leaseId'] in myLeases):
                tx['block'] = block['height']
                myCanceledLeases[tx['leaseId']] = tx

        if prevBlock is not None:
            block['previousBlockFees'] = prevBlock['fee']

        prevBlock = block

    return blocks


# put together all the active leases by address at the correct height
def getActiveLeasesAtBlock(block):
    global myLeases
    global myCanceledLeases

    activeleases = []
    totalLeased = 0
    activeLeasesPerAddress = {}

    for key in myLeases:
        currentLease = myLeases[key]

        if not(key in myCanceledLeases) or myCanceledLeases[key]['block'] > block['height']:
            activeleases.append(currentLease)

    for lease in activeleases:
        if block['height'] > lease['block'] + 1000:
            if lease['sender'] in activeLeasesPerAddress:
                activeLeasesPerAddress[lease['sender']] += lease['amount']
            else:
                activeLeasesPerAddress[lease['sender']] = lease['amount']

            totalLeased += lease['amount']

    return {'totalLeased': totalLeased, 'activeLeases': activeLeasesPerAddress}


# calculate the share of total each address will get
def distribute(activeLeases, amountTotalLeased, block):
    global payments
    global totalfee

    fee = block['fee'] * 0.4 + block['previousBlockFees'] * 0.6
    totalfee += fee

    for address in activeLeases:
        share = activeLeases[address] / amountTotalLeased
        amount = fee * share

        if address in payments:
            payments[address] += amount * (config['percentageOfFeesToDistribute'] / 100)
        else:
            payments[address] = amount * (config['percentageOfFeesToDistribute'] / 100)


# calculate some more, return total for address
def checkTotalDistributableAmount(payments):
    total = 0

    for address in payments:
        amount = payments[address]

        total += amount

    return total


# format the json and write it to a file that we named in config file
def createPayment():
    global payments
    tx = []

    for address in payments:
        if round(payments[address]) > config['minAmounttoPay']:
            paytx = {'recipient': address, 'amount': round(payments[address])}
            tx.append(paytx)

    with open(config['paymentStorage'], 'w') as outfile:
        json.dump(tx, outfile)

    print('Payments Written To ' + config['paymentStorage'])


# we use the results of the calculations and file above to calculate the token amounts we pay out.
def createTokenPayment(token):
    totalTN = 0
    global paymentFile
    tx = []

    with open(paymentFile) as p:
        parsed = json.loads(p.read())

    # amt of TN calculated automatically
    for i in parsed:
        totalTN += i['amount']

    # all the variables for tokens other than TN
    totalNERD = amtNERD
    totalCOOL = amtCOOL
    totalHT = totalTN * amtHT

    for i in parsed:
        percent = i['amount'] / totalTN

        if token == "NERD":
            amount = round(totalNERD * percent)
        elif token == "HT":
            amount = round(totalHT * percent)
        elif token == "COOL":
            amount = round(totalCOOL * percent)
        else:
            amount = i['amount']  # / 100000000

        paytx = {'recipient': i['recipient'], 'amount': amount}
        tx.append(paytx)

    with open(token + ".json", 'w') as outfile:
        json.dump(tx, outfile)

    print('payments written to ' + token + ".json")


# this we call and pass the name of the token to initiate payout.
# TODO - use config file to define which tokens to distribute
def pay(token):
    if token == "NERD":
        paymentStorage = "NERD.json"
        assetid = "skZN4EKZR4SqCL49ds2n1f5pbd4CmnWcrcH7xgCdsrb"
    elif token == "HT":
        paymentStorage = "HT.json"
        assetid = "8M54YoLc3E5h2piDtq3QzBKYPUimgSwS3xEVki8xr1gW"
    elif token == "COOL":
        paymentStorage = "COOL.json"
        assetid = "4nMNMUF6FUyEDk1DuchJjg5CK2a9SR4LzekQKLL3XozY"
    else:
        paymentStorage = "TN.json"
        assetid = None

    print(f"Reading Payment File: {paymentStorage}\n" 
          f"Asset ID: {assetid}")

    with open(paymentStorage, 'r') as f:
        payments = json.load(f)

    total = 0
    for pay in payments:
        total += pay['amount']

    if token == "COOL":
        print("Total amount " + token + " to be paid: " + str(total / 1000))
    else:
        print("Total amount " + token + " to be paid: " + str(total / 100000000))

    # do actual payment
    if config['doPayment'] == 1:
        if token == "TN":
            tx = wallet.massTransferWaves(payments,baseFee=2000000)
        else:
            tx = wallet.massTransferAssets(payments,pw.Asset(assetid),baseFee=2000000)

        print('Payment Sent, txid:\n' + str(tx))

    else:
        # this is mostly just for debugging for the time being
        tx = "Empty - Auto Payment Disabled"
        print("***No auto payment this time!***\n")

    # return total of token paid as well as the tx id
    return total, tx


# create the message we want to output based on calculations.
def createMessage(tn, nerd, cool, ht, pmts):
    if config['doPayment'] == 0:
        istest = f"\n--------------------This is Just a Test Run. No Payments Sent-------------------\n\n"
    else:
        istest = ""

    output =  (f"------------------------------------------------------------------------\n"
              f"✅🇨🇦NERD Token TN NODE Payout🇨🇦✅ - {str(datetime.date.today())} \n\n"
              f"{istest}"
              f"Node Address / alias: 3Jc52bM1i1ymjtbJZapX6gj4BtM5NXyLa2K / cashnerds\n\n"
              f"This Week's Distributions:\n"
              f"TN: {int(tn) / 100000000}\n"
              f"NERD: {int(nerd) / 100000000}\n"
              f"COOL: {int(cool) / 1000}\n"
              f"High Token: {int(ht) / 100000000}\n"
              f"Lessors: {pmts}\n\n"
              f"Thanks from NERD Token!\n"
              f"Telegram - https://t.me/TNNERD\n"
              f"Discord - https://discord.gg/ZKwzfnrKrt\n"
              f"Web - https://nerdtoken.io\n"
              f"------------------------------------------------------------------------")
    return output


# this will send the message we want to telegram using a POST request to their API.
def sendTelegramMsg(message, chatId):
    apiToken = config['telegramKey']
    apiURL = f'https://api.telegram.org/bot{apiToken}/sendMessage'
    try:
        response = requests.post(apiURL, json={'chat_id': chatId, 'text': message})
        print(f'{response.text}\n')
    except Exception as e:
        print(e)


def main():
    global payments
    global paymentFile
    global myForgedBlocks
    global myLeases
    global myCanceledLeases
    global startBlock
    global config
    global wallet

    print('Snagging me some blocks...')
    blocks = getAllBlocks()
    print('Preparing Data...')
    blocks = prepareDataStructure(blocks)

    # clear paid tx
    for block in blocks:
        txs = []

        if block['height'] < startBlock:
            for tx in block['transactions']:
                if tx['type'] == 8 or tx['type'] == 9:
                    txs.append(tx)
        else:
            txs = block['transactions']

        block['transactions'] = txs

    # save current blocks
    print('Saving Blockfile...')
    with open(config['blockStorage'], 'w') as outfile:
        json.dump(blocks, outfile)

    print('Preparing Payments...')
    if config['endBlock'] == 0:
        endBlock = requests.get(config['node'] + '/blocks/height').json()['height'] - 1
        with open('start_block.txt', 'w') as f:
            f.write(str(endBlock))
        print(f"\nEnd Block is {endBlock}\n")
    else:
        endBlock = config['endBlock']

    for block in myForgedBlocks:
        if block['height'] >= startBlock and block['height'] <= endBlock:
            blockLeaseData = getActiveLeasesAtBlock(block)
            activeLeasesForBlock = blockLeaseData['activeLeases']
            amountTotalLeased = blockLeaseData['totalLeased']

            distribute(activeLeasesForBlock, amountTotalLeased, block)

    # remove excluded addresses
    for exclude in config['excludeListTN']:
        payments[exclude] = 0
        print('excluding: ' + exclude)

    total = checkTotalDistributableAmount(payments)
    createPayment()

    numPayments = str(len(payments))

    print('Block Generated: ' + str(len(myForgedBlocks)))
    print('Number of Payments: ' + numPayments)
    print('Total TN Payment: ' + str(total / pow(10, 8)))
    print('Total Number of Leases: ' + str(len(myLeases)))
    print('Total Number of Cancelled Leases: ' + str(len(myCanceledLeases)))

    # set pyWaves config and create wallet instance for payout
    pw.setNode(node=config['node'], chain='turtlenetwork', chain_id='L')
    wallet = pw.Address(privateKey=config['privatekey'])

    print('\n')

    # calculate payments and write out files
    createTokenPayment("TN")
    createTokenPayment("NERD")
    createTokenPayment("HT")
    createTokenPayment("COOL")

    print('\n')

    # Payout each Token and get total - tx vars there in case we want to use the TX id for something
    distTN, txTN = pay("TN")
    distNERD, txNERD = pay("NERD")
    distCOOL, txCOOL = pay("COOL")
    distHT, txHT = pay("HT")

    # pass the above dist variables to createMessage, so we can formulate the output to send to telegram
    message = createMessage(distTN, distNERD, distCOOL, distHT,  numPayments)

    # take the message we put together and send it to telegram TODO - put the below in config file
    sendTelegramMsg(message, '<chatid1>')  # chatid for channel 1
    sendTelegramMsg(message, '<chatid2>')  # chatid for channel 2
    sendTelegramMsg(message, '<chatid3>')  # chatid for channel 3

    # log the last run time just in case
    print(f"***Logging date and time to lastRun.txt***")
    with open('lastRun.txt', 'w') as f:
        f.write(str(datetime.datetime.now()))


if __name__ == "__main__":
    main()
