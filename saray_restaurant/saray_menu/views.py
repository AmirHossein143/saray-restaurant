from django.shortcuts import render


def index(request):
    return render(request, 'saray_menu/index.html')


def menu(request):
    return render(request, 'saray_menu/menu.html', {
        'menu_items': [
            {'name': 'سوپ خامه', 'price': '۱۰۰۰۰۰'},
            {'name': 'سالاد فصل', 'price': '۳۰۰۰۰۰'},
            {'name': 'سالاد پاستا', 'price': '۵۰۰۰۰۰'},
        ],
        'menu_images': [
            'saray_menu/slidebar1.jpg',
            'saray_menu/slidebar2.jpg',
            'saray_menu/slidebar3.jpg',
        ],
    })
