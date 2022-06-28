import re
import json
from .hdu import *
from .scu import *
from . import exceptions

__all__ = hdu.__all__ + scu.__all__

supported_sites = ("scu", "hdu")
supported_contest_sites = ("hdu",)

normal_clients = {"scu": SOJClient, "hdu": HDUClient}
contest_clients = {"hdu": HDUContestClient}


def get_normal_client(site, auth=None):
    if site not in supported_sites:
        raise exceptions.JudgeException(f'Site "{site}" is not supported')
    return normal_clients[site](auth)


def get_contest_client(site, auth=None, contest_id=None):
    if site not in supported_contest_sites:
        raise exceptions.JudgeException(f'Site "{site}" is not supported')
    return contest_clients[site](auth, contest_id)


def get_client_by_oj_name(name, auth=None):
    res = re.match(r"^(.*?)_ct_([0-9]+)$", name)
    if res:
        site, contest_id = res.groups()
        return get_contest_client(site, auth, contest_id)
    else:
        return get_normal_client(name, auth)


def load_accounts():
    with open(OJ_CONFIG) as f:
        result = json.load(f)
    normal_accounts = {}
    for account in result["normal_accounts"]:
        site = account["site"]
        authentications = []
        for auth in account["auth"]:
            authentications.append((auth["username"], auth["password"]))
        normal_accounts[site] = authentications
    contest_accounts = {}
    for account in result["contest_accounts"]:
        site = account["site"]
        for auth in account["auth"]:
            supported_contests = auth["supported_contests"]
            for contest_id in supported_contests:
                oj_name = f"{site}_ct_{contest_id}"
                if oj_name not in contest_accounts:
                    contest_accounts[oj_name] = []
                authentications = contest_accounts.get(oj_name)
                authentications.append((auth["username"], auth["password"]))
    return normal_accounts, contest_accounts
