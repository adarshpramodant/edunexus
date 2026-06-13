with open(r'c:\Users\ADARSH\Desktop\Projects\EduNexus(main)\frontend\student_dashboard.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()
for i, l in enumerate(lines[30:38], 31):
    print(i, repr(l))
