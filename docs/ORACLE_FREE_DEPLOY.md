# Oracle 무료 VM에 Clubwire 올리기

Windows PC에서 사용하던 Clubwire를 인터넷에서 접속할 수 있는 서버로 옮기는 순서입니다. 명령에 오류가 표시되면 다음 단계로 넘어가지 말고 해당 오류부터 해결하세요. Oracle의 **Always Free Eligible**로 표시된 Ubuntu VM에 MySQL·Clubwire·Caddy를 실행하고, DuckDNS의 무료 주소로 HTTPS에 접속합니다.

예시의 `서버_IP`, `내계정`, `내클럽주소`는 본인 값으로 바꾸세요. `내클럽주소.duckdns.org`는 영어·숫자로 만든 실제 DuckDNS 주소를 뜻합니다.

**이미 사용 중인 로컬 DB를 옮길 때는 7-A**, 기록 없이 새로 시작할 때만 **7-B**를 진행합니다. 둘을 연달아 실행하면 안 됩니다. 서버를 켜는 것만으로 PC의 DB가 업로드되지는 않습니다.

## 1. Oracle 계정과 무료 VM 만들기

1. [Oracle Cloud Free Tier](https://www.oracle.com/cloud/free/)에서 계정을 만듭니다. 가입 과정에서 본인 확인과 카드 확인을 요청할 수 있습니다. 가입 전에 표시되는 조건과 카드 확인 내용을 읽으세요.
2. 콘솔에서 **Compute → Instances → Create instance**를 엽니다. 화면이 한국어라면 **컴퓨트 → 인스턴스 → 인스턴스 생성**입니다.
3. 이름은 `clubwire`처럼 정합니다. 이미지는 **Ubuntu 24.04**를 선택합니다.
4. Shape는 계정 화면에서 **Always Free Eligible**로 확인되는 **Ampere A1 Flex**를 우선 검토합니다. **1 OCPU / 메모리 6GB** 구성이 무료로 표시될 때 그 구성을 사용하면 됩니다. VM·부트 볼륨·추가 자원까지 생성 요약의 비용 표시를 확인하세요. 무료 표시가 없거나 예상 비용이 생기면 그대로 만들지 마세요.
5. 네트워크는 인터넷 게이트웨이가 있는 VCN의 **공용 서브넷**을 선택하고, **공인 IPv4 주소 할당**을 켭니다. 새 VCN을 만드는 기본 선택지를 사용할 수 있습니다.
6. SSH 키는 **새 키 쌍 생성**을 선택하고 **개인 키 다운로드**로 PC에 저장합니다. 예: `C:\Users\내계정\Downloads\clubwire.key`. 개인 키를 GitHub나 채팅에 올리지 마세요.
7. 인스턴스를 생성하고 **Running** 상태가 되면 **공인 IP 주소**를 기록합니다. Ubuntu의 SSH 사용자 이름은 보통 `ubuntu`입니다.

무료 자원의 제공 여부와 허용량은 계정·리전·현재 조건에 따라 다릅니다. 무료 자리가 없으면 다른 가용 영역이나 나중의 시도를 검토하세요. 사용량이 적은 무료 인스턴스가 회수될 수도 있으므로, 무료 VM을 항상 켜져 있는 서버로 보장할 수는 없습니다. 기존 데이터는 별도로 백업해야 합니다.

## 2. Oracle 네트워크에서 접속 허용하기

VM의 기본 VNIC·서브넷에 연결된 **Security List** 또는 사용하는 **Network Security Group**의 수신 규칙을 확인합니다.

| 용도 | 프로토콜 | 대상 포트 | 소스 |
|---|---|---|---|
| SSH 관리 | TCP | 22 | 현재 PC의 공인 IP `/32` |
| HTTP·인증서 발급 | TCP | 80 | `0.0.0.0/0` |
| HTTPS 서비스 | TCP | 443 | `0.0.0.0/0` |

소스 포트는 전체, 대상 포트에 위 번호를 입력합니다. 외부에 3306(MySQL)이나 8000(FastAPI)을 열 필요는 없습니다. 서비스 접근은 Caddy가 받습니다. PC의 공인 IP가 바뀌면 SSH 22번 규칙의 소스 IP도 수정해야 합니다.

기존 SSH 허용 규칙과 네트워크 경로를 먼저 확인한 뒤 추가하세요. 사용 중인 규칙을 한꺼번에 삭제하지 마세요.

## 3. Windows에서 SSH 접속하기

이 절의 명령은 **Windows PowerShell**에서 실행합니다.

```powershell
ssh -i "C:\Users\내계정\Downloads\clubwire.key" ubuntu@서버_IP
```

처음 접속할 때 서버 IP를 확인하고 호스트 키 신뢰 여부에 응답합니다. 접속되면 프롬프트가 `ubuntu@...` 형태로 바뀝니다. 아래의 Ubuntu 명령은 그 창 안에서 실행합니다.

Windows에서 개인 키 권한이 너무 넓다는 오류가 나면 개인 키 파일의 속성 → 보안에서 본인 계정만 읽을 수 있도록 권한을 정리한 뒤 다시 연결합니다. 개인 키 대신 `.pub` 공개 키 파일을 지정하면 접속되지 않습니다.

## 4. 서버에 Docker와 Git 설치하기

여기부터 별도 표시가 없는 명령은 **SSH로 접속한 Ubuntu 서버**에서 실행합니다.

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-v2 docker-buildx git python3
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
exit
```

`exit`로 Windows PowerShell에 돌아오면 3번의 SSH 명령으로 다시 접속합니다. 새 로그인에 Docker 그룹 권한이 적용됩니다.

```bash
docker version
docker compose version
docker buildx version
```

세 명령이 정상 출력되는지 확인합니다. 일반 Oracle VM에서는 별도 인증서 파일이나 TLS 우회 설정을 추가할 필요가 없습니다.

OS 방화벽도 확인합니다.

```bash
sudo ufw status
```

`Status: active`라면 기존 SSH 허용을 유지하면서 다음 규칙을 추가합니다.

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
```

기존 방화벽을 초기화하거나 `iptables -F`로 비우지 마세요. UFW가 비활성이라면 이 안내 때문에 새로 켤 필요는 없습니다. Oracle의 네트워크 수신 규칙과 서버의 기존 방화벽이 모두 접속을 허용해야 합니다.

## 5. DuckDNS 무료 주소 만들기

이 절은 PC의 브라우저에서 진행합니다.

1. [DuckDNS](https://www.duckdns.org/)에 로그인합니다.
2. 원하는 이름을 추가합니다. 예: `내클럽주소` → `내클럽주소.duckdns.org`.
3. 해당 항목의 **current ip**를 Oracle VM의 공인 IPv4 주소로 입력하고 **update ip**를 누릅니다. 브라우저가 자동으로 채운 PC의 IP를 그대로 사용하지 마세요.
4. IPv6를 별도로 구성하지 않았다면 잘못된 IPv6 주소를 넣지 않습니다.

DuckDNS의 토큰을 Clubwire 설정에 넣을 필요는 없습니다. 이 구성은 주소에 등록된 IP를 직접 사용하는 방식입니다. VM 공인 IP가 바뀌면 DuckDNS에서 새 IP로 수정하면 같은 주소를 계속 쓸 수 있습니다.

## 6. 코드와 서버 설정 준비하기

Ubuntu SSH 창에서 실행합니다.

```bash
git clone --branch deploy/oracle-free https://github.com/preferJ/clubwire.git
cd clubwire
python3 scripts/init_deploy_env.py --domain 내클럽주소.duckdns.org
```

도메인에는 `https://`나 `/c/sanha`를 붙이지 않습니다. 이 명령은 `deploy/oracle.env`에 서버용 DB 암호와 서명 키를 생성합니다. 기존 설정이 있으면 기존 값을 보존합니다.

OpenAI를 사용할 때만 다음 파일을 엽니다.

```bash
nano deploy/oracle.env
```

`OPENAI_API_KEY=` 뒤에 API 키를 입력하고 `Ctrl+O` → Enter로 저장한 뒤 `Ctrl+X`로 나옵니다. 비워 두면 기본형 기사로 동작합니다. OpenAI API 비용은 서버의 무료 여부와 별개입니다.

`deploy/oracle.env`는 서버의 비밀 설정입니다. Git에 추가하거나 화면 전체를 공유하지 마세요. 로컬 PC의 `.env`를 이 파일 위에 그대로 덮어쓰지도 마세요. 로컬 DB 접속 주소와 서버 DB 암호가 다르기 때문입니다.

## 7-A. 기존 PC의 DB를 그대로 옮기기

현재 PC의 클럽·선수·경기·기사·설정·관리자 계정을 옮기는 경로입니다. **이 경로에서는 초기화 스크립트를 실행하지 않습니다.**

### PC에서 전체 DB 내보내기

1. 로컬 백엔드를 종료하고 DB를 수정하는 다른 프로그램도 멈춥니다.
2. **MySQL Workbench → Server → Data Export**를 엽니다.
3. `clubwire` 스키마의 **모든 테이블**을 선택합니다. `CLUB`, `CLUB_ADMIN`, 설정 테이블과 `alembic_version`도 포함해야 합니다.
4. **Dump Structure and Data**와 **Export to Self-Contained File**을 선택하고, 저장 파일을 `C:\Users\내계정\Downloads\clubwire-full.sql`처럼 지정합니다.
5. **Start Export**를 누르고 오류 없이 완료됐는지 확인합니다. 원본 파일은 PC에 보관합니다.

`scripts/reset_ypr_test.py`가 만든 복구 SQL은 특정 클럽 초기화의 되돌리기용이며, 원래 DB와 남아 있는 클럽·설정을 전제로 합니다. 위와 같은 **전체 구조+데이터 이전 백업을 대신할 수 없습니다.**

Windows MySQL은 테이블 이름을 소문자로 저장할 수 있고, 이 서버는 대소문자를 구분합니다. 아래에서 전용 스크립트로 Clubwire 테이블 이름을 맞춘 **새 파일**을 만든 뒤 가져옵니다. SQL 전체를 단순 대문자 변환하면 선수 이름과 데이터까지 손상될 수 있습니다.

### 서버로 전송하고 가져오기

**새 Windows PowerShell 창**에서 실행합니다.

```powershell
scp -i "C:\Users\내계정\Downloads\clubwire.key" "C:\Users\내계정\Downloads\clubwire-full.sql" ubuntu@서버_IP:~/clubwire-full.sql
```

다시 **Ubuntu SSH 창**에서 프로젝트 폴더로 이동합니다. 아직 앱과 Caddy는 띄우지 않고 DB만 시작합니다.

```bash
cd ~/clubwire
umask 077
chmod 600 ~/clubwire-full.sql
python3 scripts/normalize_mysql_dump.py ~/clubwire-full.sql ~/clubwire-full-linux.sql
chmod 600 ~/clubwire-full-linux.sql
bash deploy/cloud.sh up -d db
bash deploy/cloud.sh ps
```

정규화 명령은 원본을 유지하고 Clubwire 테이블 식별자의 대소문자만 맞춘 새 파일을 만듭니다. 기존 출력 파일을 덮어쓰지 않으므로 다시 실행할 때는 다른 출력 파일 이름을 지정하고 이후 가져오기 경로도 맞추세요. 오류가 나면 가져오기를 진행하지 않습니다.

DB 상태가 `healthy`가 될 때까지 기다립니다. 처음 생성할 때는 시간이 걸릴 수 있습니다.

```bash
bash deploy/cloud.sh logs --tail=50 db
```

다음 명령은 **새 서버의 비어 있는 `clubwire` DB로 가져오는 명령**입니다. 서버에 이미 운영 데이터가 있다면 먼저 10번 백업을 만든 뒤 별도의 복구 절차를 진행해야 합니다.

```bash
bash deploy/cloud.sh exec -T db sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql --default-character-set=utf8mb4 -uroot clubwire' < ~/clubwire-full-linux.sql
```

명령에 오류가 없었는지 확인하고, 클럽·선수 수가 예상한 값인지 조회합니다.

```bash
bash deploy/cloud.sh exec -T db sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot clubwire -e "SELECT COUNT(*) AS clubs FROM CLUB; SELECT COUNT(*) AS members FROM MEMBER;"'
```

가져온 DB에는 기존 관리자 암호도 들어 있습니다. 기본 암호를 그대로 공개하지 않도록, 앱과 Caddy를 띄우기 전에 다음과 같이 스키마를 최신화하고 강한 관리자 암호를 설정합니다. 새 암호 입력은 화면과 쉘 명령 기록에 표시되지 않습니다.

```bash
bash deploy/cloud.sh build app
bash deploy/cloud.sh run --rm --no-deps app alembic upgrade head
read -rsp "새 관리자 암호: " CW_ADMIN_PIN
echo
export CW_ADMIN_PIN
bash deploy/cloud.sh run --rm --no-deps -e CW_ADMIN_PIN app sh -c 'python -m app.cli set-pin --slug sanha --pin "$CW_ADMIN_PIN"'
unset CW_ADMIN_PIN
```

이제 **8번으로 이동**합니다. 7-B는 실행하지 않습니다.

## 7-B. 기록 없이 새 DB로 시작하기

PC의 기록을 옮기려면 이 절을 건너뛰고 7-A를 사용합니다. 다음 과정은 **처음 한 번 수동으로만 실행**합니다. 평소 서버 시작 명령에 넣으면 안 됩니다.

먼저 DB와 앱 이미지를 준비하고 스키마를 생성합니다. 앱 서버는 아직 실행하지 않습니다.

```bash
cd ~/clubwire
bash deploy/cloud.sh up -d db
bash deploy/cloud.sh build app
bash deploy/cloud.sh ps
```

DB가 `healthy`가 된 것을 확인한 뒤 마이그레이션을 실행합니다. 아직 준비 중이면 `bash deploy/cloud.sh logs --tail=50 db`로 상태를 확인하며 기다립니다.

```bash
bash deploy/cloud.sh run --rm --no-deps app alembic upgrade head
```

공개 전에 사용할 관리자 암호를 입력합니다. 숫자 네 자리 기본값을 재사용하지 말고 충분히 긴 암호를 정하세요. 입력 값은 화면과 쉘 명령 기록에 표시되지 않습니다.

```bash
read -rsp "새 관리자 암호: " CW_ADMIN_PIN
echo
export CW_ADMIN_PIN
bash deploy/cloud.sh run --rm --no-deps -e CW_ADMIN_PIN app sh -c 'python -m app.cli create-club --slug sanha --name "YPR" --pin "$CW_ADMIN_PIN"'
unset CW_ADMIN_PIN
```

**원본 선수단과 테스트 안내 기사로 새로 시작하려는 경우에만** 다음 초기화를 실행합니다. 이미 경기를 입력했거나 이전 DB를 가져왔다면 실행하지 마세요. 초기화는 해당 클럽의 기존 경기·기사·선수 데이터를 지웁니다.

```bash
umask 077
mkdir -p "$HOME/clubwire-backups"
bash deploy/cloud.sh run --rm --no-deps app python -m scripts.reset_ypr_test --club sanha
```

위 명령은 미리보기입니다. 대상이 새로 만든 `sanha` 클럽인 것을 확인한 뒤 실제 적용합니다. 초기화 전 복구 파일을 서버 사용자 소유의 백업 폴더에 남기기 위해 볼륨과 실행 사용자를 지정합니다.

```bash
bash deploy/cloud.sh run --rm --no-deps --user "$(id -u):$(id -g)" -v "$HOME/clubwire-backups:/backups" app python -m scripts.reset_ypr_test --club sanha --backup-dir /backups --apply
```

이 초기화 명령은 재시작이나 업데이트 때 다시 실행하지 않습니다. 새 클럽 생성 시 설정한 관리자 암호는 초기화 후에도 유지됩니다.

## 8. HTTPS로 서비스 시작하기

7-A의 DB 가져오기 또는 7-B의 최초 준비 중 하나를 마친 뒤 실행합니다.

```bash
cd ~/clubwire
bash deploy/cloud.sh up -d --build
bash deploy/cloud.sh ps
bash deploy/cloud.sh logs --tail=100 app caddy
```

앱 시작 시 `alembic upgrade head`가 실행되어 DB 스키마를 최신화합니다. **일반 시작은 데이터 초기화를 하지 않습니다.** MySQL 데이터와 Caddy 인증서는 Docker 볼륨에 보관됩니다.

DNS가 VM을 가리키고 외부 TCP 80·443이 열려 있으면 Caddy가 HTTPS 인증서를 자동으로 발급받습니다. 처음에는 DNS 반영과 인증서 발급을 기다린 뒤 확인합니다.

```bash
curl -fsS https://내클럽주소.duckdns.org/health
curl -fsS https://내클럽주소.duckdns.org/api/clubs/sanha
```

첫 요청은 `{"status":"ok"}`, 두 번째는 `clubSlug`가 `sanha`인 클럽 정보를 반환해야 합니다. 두 번째 요청은 DB를 사용하는 조회입니다.

PC나 폰 브라우저에서 다음 주소를 엽니다.

```text
https://내클럽주소.duckdns.org/c/sanha
```

다른 클럽 slug를 사용했다면 `sanha`를 그 값으로 바꿉니다. 관리자 로그인, 선수단·일정·기사 조회를 확인합니다.

관리자 암호는 공개 전에 7-A 또는 7-B에서 설정한 값을 사용합니다. 이후 변경은 관리자 설정 화면에서 할 수 있습니다.

## 9. 재시작·업데이트

서버가 재부팅되면 Docker와 서비스의 재시작 정책이 적용됩니다. 필요할 때 수동으로 다시 켜는 명령은 다음과 같습니다.

```bash
cd ~/clubwire
bash deploy/cloud.sh up -d
```

코드를 업데이트할 때는 먼저 10번의 전체 백업을 만든 뒤 실행합니다.

```bash
cd ~/clubwire
git pull --ff-only origin deploy/oracle-free
bash deploy/cloud.sh up -d --build
bash deploy/cloud.sh ps
```

평소에는 `reset_ypr_test --apply`를 실행하지 않습니다. `docker compose down -v`, `docker volume prune` 같은 볼륨 삭제 명령도 사용하지 마세요. DB가 담긴 볼륨을 삭제하면 코드만 다시 내려받아서는 기록이 복구되지 않습니다.

## 10. 전체 DB 백업과 서버 밖 보관

Ubuntu 서버에서 실행합니다. 백업 파일은 Git 폴더 밖에 권한을 제한해 저장합니다.

```bash
cd ~/clubwire
umask 077
mkdir -p "$HOME/clubwire-backups"
CW_BACKUP_FILE="$HOME/clubwire-backups/clubwire-$(date +%Y%m%d-%H%M%S).sql"
if bash deploy/cloud.sh exec -T db sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysqldump --default-character-set=utf8mb4 --single-transaction --set-gtid-purged=OFF --no-tablespaces -uroot clubwire' > "$CW_BACKUP_FILE.tmp"; then
  mv "$CW_BACKUP_FILE.tmp" "$CW_BACKUP_FILE"
  echo "백업 완료: $CW_BACKUP_FILE"
else
  rm -f "$CW_BACKUP_FILE.tmp"
  echo "백업 실패: DB 로그와 디스크 여유 공간을 확인하세요."
fi
```

출력된 파일 이름을 확인한 뒤 **Windows PowerShell**에서 PC로 복사합니다.

```powershell
scp -i "C:\Users\내계정\Downloads\clubwire.key" ubuntu@서버_IP:~/clubwire-backups/clubwire-생성일시.sql "C:\Users\내계정\Downloads\"
```

VM이 회수·삭제되면 같은 VM 안의 백업도 잃을 수 있습니다. PC 등 서버 밖에 보관하고, `deploy/oracle.env`와 SSH 개인 키도 각각 안전하게 보관하세요. DB 백업에는 선수 정보와 관리자 암호 해시 등이 들어 있으므로 GitHub에 올리지 않습니다.

## 11. 접속되지 않을 때

- **SSH 연결이 안 됨:** VM의 Running 상태, 공인 IP, 개인 키, 사용자 `ubuntu`, 22번 수신 규칙의 PC IP를 확인합니다.
- **사이트 연결이 안 됨:** DuckDNS의 IP와 VM 공인 IP가 같은지, Oracle TCP 80·443 규칙과 OS 방화벽을 확인합니다.
- **인증서 오류:** 도메인 철자·DNS·포트부터 확인하고 `bash deploy/cloud.sh logs --tail=100 caddy`를 확인합니다. 문제를 고치지 않은 채 반복 재시도하면 인증서 발급 제한에 걸릴 수 있습니다.
- **502 또는 앱 unhealthy:** `bash deploy/cloud.sh logs --tail=100 app db`로 마이그레이션·DB 오류를 확인합니다. Windows 덤프를 옮겼다면 테이블 이름의 대소문자도 확인합니다.
- **Docker 권한 오류:** 그룹 추가 후 SSH에서 완전히 로그아웃하고 다시 접속했는지 확인합니다.
- **OpenAI 기사만 기본형으로 나옴:** 관리자 기사 검토의 실패 원인과 API 크레딧을 확인합니다. 서버 무료 구성과 OpenAI API 결제는 별개입니다.

공식 참고: [Oracle Free Tier 문서](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier.htm), [Always Free 자원 안내](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm), [DuckDNS](https://www.duckdns.org/), [Caddy 자동 HTTPS](https://caddyserver.com/docs/automatic-https). 이 문서는 현재 Oracle 계정의 자원 재고·요금·무료 자격을 대신 확인하지 않으므로 생성 화면과 공식 조건을 기준으로 진행하세요.

## 배포 파일 검증 범위

제공한 Docker 이미지는 별도 Linux amd64 컨테이너에서 실제 빌드했습니다. MySQL 신규 마이그레이션, 비루트 사용자 실행, DB를 사용하는 API와 React 화면 제공, 앱 재시작 후 데이터 보존, Windows식 테이블명 덤프 정규화 후 전체 DB 가져오기, Caddy 구성 검증을 통과했습니다. Python 테스트는 76개와 하위 테스트 6개를 통과했습니다.

이 검증은 Oracle 계정에 VM을 만들거나 실제 DuckDNS 도메인의 HTTPS 인증서를 발급받은 것은 아닙니다. Oracle ARM VM에서의 빌드, 무료 자원 할당 가능 여부, 본인 도메인의 DNS·방화벽·인증서는 위 절차에 따라 실제 서버에서 확인해야 합니다.
