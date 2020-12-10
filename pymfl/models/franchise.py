class Franchise():
    """Struct representing franchise object returned from MFL"""

    def __init__(self, franchise_json):
        self.name = franchise_json['name']
        self.franchise_id = franchise_json['id']
        self.blind_bid_dollars = franchise_json['bbidAvailableBalance']
        self.division_id = franchise_json['division']
        self.roster = {}

    def __repr__(self):
        id_str = f'franchise id: {self.franchise_id}'
        name_str = f'name: {self.name}'
        bbd_str = f'blind bid dollars: {self.blind_bid_dollars}'
        division_str = f'division id: {self.division_id}'

        return '{' + ',\n\t'.join([id_str, name_str, bbd_str, division_str]) + '}'
    
    def __str__(self):
        return self.__repr__()
