from time import time, sleep

from algosdk import account, encoding
from algosdk.logic import get_application_address
from algosdk.future import transaction
from auction.operations import createAuctionApp, setupAuctionApp, placeBid, closeAuction
from auction.util import (
    getBalances,
    getAppGlobalState,
    getLastBlockTimestamp,
    checkAssetPossession,
    waitForTransaction
)
from auction.testing.setup import getAlgodClient
from auction.testing.resources import (
    getTemporaryAccount,
    optInToAsset,
    createDummyAsset,
)


def simple_auction():
    client = getAlgodClient()

    print("Generating temporary accounts...")
    creator = getTemporaryAccount(client)
    originalSeller = getTemporaryAccount(client)
    seller = getTemporaryAccount(client)
    bidder = getTemporaryAccount(client)

    print("Alice (NFT Creator account):", originalSeller.getAddress())
    print("Jack (seller): ", seller.getAddress())
    print("Bob (auction creator account):", creator.getAddress())
    print("Carla (bidder account)", bidder.getAddress(), "\n")

    print("Alice is generating an example NFT...")
    nftAmount = 1
    nftID = createDummyAsset(client, nftAmount, originalSeller)
    print("The NFT ID is", nftID)
    print("Alice's balances:", getBalances(client, originalSeller.getAddress()), "\n")
    print("Alice NFT Ownership status : ", checkAssetPossession(client, originalSeller.getAddress(), nftID))

    initialCreatorAmount = getBalances(client, originalSeller.getAddress())[0]

    print("Alice sold the NFT to Jack...")
    print("Jack is opting into the NFT")
    optInToAsset(client, nftID, seller)

    payTxn = transaction.AssetTransferTxn(
        sender=originalSeller.getAddress(),
        receiver=seller.getAddress(),
        amt=1,
        index=nftID,
        sp=client.suggested_params()
    ) 

    transaction.assign_group_id([payTxn])

    signedPayTxn = payTxn.sign(originalSeller.getPrivateKey())

    client.send_transactions([signedPayTxn])

    waitForTransaction(client, signedPayTxn.get_txid())
    print("Alice's NFT Ownership status : ", checkAssetPossession(client, originalSeller.getAddress(), nftID))
    print("Jack's NFT Ownership status : ", checkAssetPossession(client, seller.getAddress(), nftID))

    startTime = int(time()) + 10  # start time is 10 seconds in the future
    endTime = startTime + 30  # end time is 30 seconds after start
    reserve = 1_000_000  # 1 Algo
    increment = 100_000  # 0.1 Algo
    royaltyPercentage = 10
    print("Bob is creating an auction that lasts 30 seconds to auction off the NFT...")
    appID = createAuctionApp(
        client=client,
        sender=creator,
        seller=seller.getAddress(),
        nftID=nftID,
        startTime=startTime,
        endTime=endTime,
        reserve=reserve,
        minBidIncrement=increment,
        royaltyPercentage=royaltyPercentage,
        nftCreator=originalSeller.getAddress()
    )
    print(
        "Done. The auction app ID is",
        appID,
        "and the escrow account is",
        get_application_address(appID),
        "\n",
    )

    print("Jack is setting up and funding NFT auction...")
    setupAuctionApp(
        client=client,
        appID=appID,
        funder=creator,
        nftHolder=seller,
        nftID=nftID,
        nftAmount=nftAmount,
    )
    print("Done\n")

    sellerBalancesBefore = getBalances(client, seller.getAddress())
    sellerAlgosBefore = sellerBalancesBefore[0]
    print("Jack's balances:", sellerBalancesBefore)

    _, lastRoundTime = getLastBlockTimestamp(client)
    if lastRoundTime < startTime + 5:
        sleep(startTime + 5 - lastRoundTime)
    actualAppBalancesBefore = getBalances(client, get_application_address(appID))
    print("Auction escrow balances:", actualAppBalancesBefore, "\n")

    bidAmount = reserve
    bidderBalancesBefore = getBalances(client, bidder.getAddress())
    bidderAlgosBefore = bidderBalancesBefore[0]
    print("Carla wants to bid on NFT, her balances:", bidderBalancesBefore)
    print("Carla is placing bid for", bidAmount, "microAlgos")

    placeBid(client=client, appID=appID, bidder=bidder, bidAmount=bidAmount)

    print("Carla is opting into NFT with ID", nftID)

    optInToAsset(client, nftID, bidder)

    print("Done\n")

    _, lastRoundTime = getLastBlockTimestamp(client)
    if lastRoundTime < endTime + 5:
        waitTime = endTime + 5 - lastRoundTime
        print("Waiting {} seconds for the auction to finish\n".format(waitTime))
        sleep(waitTime)

    print("Jack is closing out the auction\n")
    closeAuction(client, appID, seller)

    actualAppBalances = getBalances(client, get_application_address(appID))
    expectedAppBalances = {0: 0}
    print("The auction escrow now holds the following:", actualAppBalances)
    assert actualAppBalances == expectedAppBalances

    bidderNftBalance = getBalances(client, bidder.getAddress())[nftID]
    assert bidderNftBalance == nftAmount

    actualSellerBalances = getBalances(client, seller.getAddress())
    print("Jack's balances after auction: ", actualSellerBalances, " Algos")
    actualBidderBalances = getBalances(client, bidder.getAddress())
    print("Carla's balances after auction: ", actualBidderBalances, " Algos")
    assert len(actualSellerBalances) == 2
    print("NFT Creator's royalty")
    actualNFTCreatorBalances = getBalances(client, originalSeller.getAddress())
    print("Alice's balances after auction: ", actualNFTCreatorBalances, " Algos")
    print("Royalties paid to NFT Creator: ", actualNFTCreatorBalances[0] - initialCreatorAmount)

    # seller should receive the bid amount, minus the txn fee
    assert actualSellerBalances[0] >= sellerAlgosBefore + bidAmount - 1_000
    assert actualSellerBalances[nftID] == 0


simple_auction()
