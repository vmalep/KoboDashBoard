from django.shortcuts import render, redirect
from .forms import RegistrationForm


def register(request):
    if request.user.is_authenticated:
        return redirect('/dashboard/')
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('/accounts/pending/')
    else:
        form = RegistrationForm()
    return render(request, 'accounts/register.html', {'form': form})


def pending_approval(request):
    return render(request, 'accounts/pending_approval.html')
