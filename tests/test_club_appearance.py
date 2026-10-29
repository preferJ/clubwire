"""클럽 외형: 팀별 저장, 이미지 정규화, 실시간 반영과 기존 데이터 보존."""
import base64
from io import BytesIO
from uuid import uuid4

import pytest
from PIL import Image, PngImagePlugin
from sqlalchemy import select

from app.models import Club, Member


def _club(make_club):
    return make_club('crest-' + uuid4().hex[:10])


def _image(color=(24, 48, 96, 128), size=(800, 400), fmt='PNG', metadata=False):
    image = Image.new('RGBA', size, color)
    if fmt == 'JPEG':
        image = image.convert('RGB')
    output = BytesIO()
    options = {}
    if metadata and fmt == 'PNG':
        info = PngImagePlugin.PngInfo()
        info.add_text('Comment', 'discard this metadata')
        options['pnginfo'] = info
    image.save(output, format=fmt, **options)
    mime = {'PNG': 'image/png', 'JPEG': 'image/jpeg', 'WEBP': 'image/webp'}[fmt]
    return 'data:' + mime + ';base64,' + base64.b64encode(output.getvalue()).decode()


def _design(**changes):
    return {'mode': 'design', 'shape': 'shield', 'pattern': 'stripes',
            'primaryColor': '#c81e2b', 'secondaryColor': '#ffffff', 'textColor': '#ffffff',
            'text': 'YPR', 'symbol': 'ball', **changes}


def test_existing_club_defaults_and_public_metadata(make_club, db):
    api = _club(make_club)
    cid = api.ok(api.get(''))['clubId']
    stored = db.get(Club, cid)
    assert stored.crest_config is None and stored.default_theme is None and stored.crest_image is None
    appearance = api.ok(api.get('/appearance', admin=False))
    assert appearance['crest']['mode'] == 'auto' and appearance['defaultTheme'] == 'dark'
    assert appearance['imageUrl'] is None and appearance['updatedAt'] is None
    assert api.ok(api.get('', admin=False))['appearance'] == appearance
    assert api.get('/appearance/crest', admin=False).status_code == 404
    assert api.ok(api.patch('/admin/appearance', {})) == appearance


def test_appearance_is_admin_only_and_club_scoped(make_club, db):
    a, b = _club(make_club), _club(make_club)
    before_b = b.ok(b.get('/appearance'))
    assert a.c.patch(a.url('/admin/appearance'), json={'defaultTheme': 'light'}).status_code == 401
    assert a.c.patch(a.url('/admin/appearance'), headers={'Authorization': f'Bearer {b.token}'},
                     json={'defaultTheme': 'light'}).status_code == 403
    mid = a.ok(a.post('/members', {'name': '보존할 선수'}), 201)['memberId']
    saved = a.ok(a.patch('/admin/appearance', {'crest': _design(shape='circle'), 'defaultTheme': 'light'}))
    assert saved['crest'] == _design(shape='circle') and saved['defaultTheme'] == 'light'
    assert saved['updatedAt'] and saved['imageUrl'] is None
    assert a.ok(a.get('/appearance', admin=False)) == saved
    assert b.ok(b.get('/appearance')) == before_b
    assert a.ok(a.get('', admin=False))['appearance'] == saved
    assert db.get(Member, mid).name == '보존할 선수'
    assert db.get(Member, mid).club_id == a.ok(a.get(''))['clubId']
    # 같은 설정 재저장은 시각을 바꾸거나 새 레코드를 만들지 않는다.
    assert a.ok(a.patch('/admin/appearance', {'crest': _design(shape='circle'), 'defaultTheme': 'light'})) == saved


@pytest.mark.parametrize('body', [
    {'defaultTheme': 'purple'}, {'crest': {'mode': 'svg'}}, {'crest': {'shape': 'script'}},
    {'crest': {'primaryColor': 'url(javascript:1)'}}, {'crest': {'text': '<svg>'}},
    {'crest': {'text': '1234567'}}, {'crest': {'imageUrl': 'https://example.com/logo.svg'}},
])
def test_invalid_design_is_rejected_without_partial_save(make_club, body):
    api = _club(make_club)
    before = api.ok(api.get('/appearance'))
    assert api.patch('/admin/appearance', body).status_code == 422
    assert api.ok(api.get('/appearance')) == before


@pytest.mark.parametrize('field', ['crest', 'defaultTheme'])
def test_null_setting_is_a_readable_error_not_server_failure(make_club, field):
    api = _club(make_club)
    response = api.patch('/admin/appearance', {field: None})
    assert response.status_code == 400 and response.json()['error']['code'] == 'INVALID_CLUB_APPEARANCE'


def test_missing_image_rejects_whole_update(make_club):
    api = _club(make_club)
    before = api.ok(api.get('/appearance'))
    response = api.patch('/admin/appearance', {'crest': _design(mode='image'), 'defaultTheme': 'light'})
    assert response.status_code == 400 and response.json()['error']['code'] == 'CREST_IMAGE_REQUIRED'
    assert api.ok(api.get('/appearance')) == before


@pytest.mark.parametrize('fmt', ['PNG', 'JPEG', 'WEBP'])
def test_upload_is_normalized_and_served_as_png(make_club, fmt):
    api = _club(make_club)
    saved = api.ok(api.patch('/admin/appearance', {
        'crest': _design(mode='image'), 'imageDataUrl': _image(fmt=fmt, metadata=True),
    }))
    assert saved['crest']['mode'] == 'image' and saved['imageUrl'].startswith(api.url('/appearance/crest?v='))
    assert 'imageDataUrl' not in saved
    response = api.c.get(saved['imageUrl'])
    assert response.status_code == 200 and response.headers['content-type'] == 'image/png'
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert 'immutable' in response.headers['cache-control']
    with Image.open(BytesIO(response.content)) as normalized:
        assert normalized.size == (512, 256) and normalized.format == 'PNG'
        assert 'Comment' not in normalized.info and not normalized.getexif()
        if fmt == 'PNG':
            assert normalized.convert('RGBA').getpixel((0, 0))[3] == 128
    etag = response.headers['etag']
    cached = api.c.get(saved['imageUrl'], headers={'If-None-Match': etag})
    assert cached.status_code == 304 and not cached.content
    assert api.get('/appearance/crest', admin=False).headers['cache-control'] == 'no-cache'
    # 새 이미지로 교체되면 URL과 ETag가 바뀌고 이전 버전 주소는 장기 캐시하지 않는다.
    replaced = api.ok(api.patch('/admin/appearance', {'imageDataUrl': _image(color=(192, 16, 32, 255))}))
    assert replaced['imageUrl'] != saved['imageUrl']
    stale_url = api.c.get(saved['imageUrl'])
    assert stale_url.headers['cache-control'] == 'no-cache' and stale_url.headers['etag'] != etag
    # 이미지 삭제는 모드 변경과 한 번에 저장한다.
    cleared = api.ok(api.patch('/admin/appearance', {'crest': {'mode': 'auto'}, 'imageDataUrl': None}))
    assert cleared['crest']['mode'] == 'auto' and cleared['imageUrl'] is None
    assert api.get('/appearance/crest', admin=False).status_code == 404


@pytest.mark.parametrize('data', [
    'https://example.com/logo.png', 'data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=',
    'data:image/png;base64,not-base64', 'data:image/png;base64,' + base64.b64encode(b'not an image').decode(),
])
def test_invalid_image_does_not_change_existing_design_or_theme(make_club, data):
    api = _club(make_club)
    before = api.ok(api.patch('/admin/appearance', {'crest': _design()}))
    assert api.patch('/admin/appearance', {'crest': _design(mode='image'), 'imageDataUrl': data,
                                         'defaultTheme': 'light'}).status_code == 400
    assert api.ok(api.get('/appearance')) == before


def test_oversized_and_animated_images_are_rejected(make_club):
    api = _club(make_club)
    too_large = 'data:image/png;base64,' + base64.b64encode(b'x' * (2 * 1024 * 1024 + 1)).decode()
    assert api.patch('/admin/appearance', {'imageDataUrl': too_large}).status_code == 400
    assert api.patch('/admin/appearance', {'imageDataUrl': _image(size=(4097, 1))}).status_code == 400
    output = BytesIO()
    Image.new('RGBA', (8, 8), 'red').save(output, format='PNG', save_all=True,
                                       append_images=[Image.new('RGBA', (8, 8), 'blue')], duration=100, loop=0)
    animated = 'data:image/png;base64,' + base64.b64encode(output.getvalue()).decode()
    response = api.patch('/admin/appearance', {'imageDataUrl': animated})
    assert response.status_code == 400 and response.json()['error']['code'] == 'ANIMATED_CREST_IMAGE'
    assert api.ok(api.get('/appearance'))['updatedAt'] is None


def test_change_emits_scoped_websocket_event_and_removed_club_is_inaccessible(make_club, client):
    api = _club(make_club)
    with client.websocket_connect(f'/ws/clubs/{api.slug}') as ws:
        assert ws.receive_json()['type'] == 'HELLO'
        api.ok(api.patch('/admin/appearance', {'crest': _design(), 'defaultTheme': 'light'}))
        assert ws.receive_json() == {'type': 'CLUB_APPEARANCE_UPDATED'}
    # 제거된 팀의 외형도 기존 club_dep를 통해 차단된다.
    auth = client.post('/api/admin/auth', json={'password': '7418'}).json()
    headers = {'Authorization': f"Bearer {auth['accessToken']}"}
    cid = api.ok(api.get(''))['clubId']
    assert client.delete(f'/api/admin/clubs/{cid}', headers=headers).status_code == 200
    assert api.get('/appearance', admin=False).status_code == 404
    assert api.patch('/admin/appearance', {'defaultTheme': 'dark'}).status_code == 404
    assert client.post(f'/api/admin/clubs/{cid}/restore', headers=headers).status_code == 200
    assert api.ok(api.get('/appearance'))['crest']['text'] == 'YPR'
