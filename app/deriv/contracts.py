class ContractType:
    # Rise/Fall
    CALL = "CALL"
    PUT = "PUT"
    
    # Digits
    DIGITDIFF = "DIGITDIFF"
    DIGITMATCH = "DIGITMATCH"
    DIGITEVEN = "DIGITEVEN"
    DIGITODD = "DIGITODD"
    DIGITOVER = "DIGITOVER"
    DIGITUNDER = "DIGITUNDER"
    
    # Multipliers
    MULTUP = "MULTUP"
    MULTDOWN = "MULTDOWN"
    
    # Touches
    ONETOUCH = "ONETOUCH"
    NOTOUCH = "NOTOUCH"
    
    # High/Low
    RANGE = "RANGE"
    UPORDOWN = "UPORDOWN"
    EXPIRYRANGE = "EXPIRYRANGE"
    EXPIRYMISS = "EXPIRYMISS"

ACTION_TO_CONTRACT = {
    "CALL": ContractType.CALL,
    "PUT": ContractType.PUT,
    "BUY": ContractType.CALL,
    "SELL": ContractType.PUT,
    "UP": ContractType.CALL,
    "DOWN": ContractType.PUT,
    
    "MATCH": ContractType.DIGITMATCH,
    "DIFF": ContractType.DIGITDIFF,
    "EVEN": ContractType.DIGITEVEN,
    "ODD": ContractType.DIGITODD,
    "OVER": ContractType.DIGITOVER,
    "UNDER": ContractType.DIGITUNDER,
    
    "MULTUP": ContractType.MULTUP,
    "MULTDOWN": ContractType.MULTDOWN,
    
    "TOUCH": ContractType.ONETOUCH,
    "NOTOUCH": ContractType.NOTOUCH
}
